# -*- coding: utf-8 -*-
"""一次性数据修复：rpt_gap_by_file 报表 SQL 引用 duckdb 中不存在的
flow_reconcile_gap 表（该表在 meta.sqlite），报表运行必然报错。

修复：替换为基于 fact_stock_flow/fact_inventory 在 duckdb 内直接重算的
gap 汇总 SQL（口径与 flow_gov.reconcile() 一致）。幂等：仅当旧 SQL
引用 flow_reconcile_gap 时更新。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories import meta_tx  # noqa: E402

GAP_BY_FILE_SQL = """
WITH flow AS (
  SELECT material_id,
         SUM(CASE WHEN flow_type='IN' THEN COALESCE(quantity,0) ELSE 0 END) AS qty_in,
         SUM(CASE WHEN flow_type='OUT' THEN COALESCE(quantity,0) ELSE 0 END) AS qty_out
  FROM fact_stock_flow GROUP BY material_id
),
inv AS (
  SELECT material_id,
         SUM(COALESCE(stock_qty,0)) AS stock_qty,
         SUM(COALESCE(opening_qty,0)) AS opening_qty,
         ANY_VALUE(source_file) AS source_file
  FROM fact_inventory GROUP BY material_id
)
SELECT g.source_file, COUNT(*) AS gap_cnt, ROUND(SUM(g.gap), 2) AS gap_qty
FROM (
  SELECT COALESCE(i.material_id, f.material_id) AS material_id,
         (COALESCE(f.qty_in,0)-COALESCE(f.qty_out,0))
           - (COALESCE(i.stock_qty,0)-COALESCE(i.opening_qty,0)) AS gap,
         i.source_file
  FROM inv i FULL OUTER JOIN flow f USING (material_id)
  WHERE ABS((COALESCE(f.qty_in,0)-COALESCE(f.qty_out,0))
            - (COALESCE(i.stock_qty,0)-COALESCE(i.opening_qty,0))) > 0.01
) g
GROUP BY g.source_file ORDER BY gap_cnt DESC
""".strip()


def main() -> None:
    with meta_tx() as con:
        row = con.execute(
            "SELECT report_id, name, query_sql FROM report_definition WHERE report_id='rpt_gap_by_file'"
        ).fetchone()
        if not row:
            print("rpt_gap_by_file not found; nothing to do")
            return
        old = row["query_sql"] or ""
        if "flow_reconcile_gap" not in old:
            print("rpt_gap_by_file 已是 duckdb 可用 SQL；跳过")
            return
        con.execute(
            "UPDATE report_definition SET query_sql=? WHERE report_id='rpt_gap_by_file'",
            [GAP_BY_FILE_SQL],
        )
        print(f"已修复 rpt_gap_by_file：{row['name']}")
        print(f"  旧 SQL（引用 flow_reconcile_gap）{len(old)} 字符 → 新 SQL {len(GAP_BY_FILE_SQL)} 字符")


if __name__ == "__main__":
    main()
