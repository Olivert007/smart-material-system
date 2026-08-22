# -*- coding: utf-8 -*-
"""补齐演示库趋势分析缺数据板块（可重复执行，幂等）。

背景
----
build_demo_env.py 只发布库存与流水两个域，样例台账没有区域/最低库存列，
也没有资产清查数据，导致趋势分析里以下图表为空：
  库存区域分布、低库存 TOP（库存 < 最低库存）、资产公司分布、
  资产区域（域）分布、资产购买年份分布

本脚本对演示库做确定性补齐：
1. region：从 location 关键字推导（溪洛渡 / 向家坝 / 成都 / 其他）
2. min_qty：结合 stock_qty 与 material_id 稳定哈希合成，制造少量真实低库存项
3. fact_asset：基于 dim_material 合成资产清查演示行（公司/区域/购买年份分布）

用法
----
    python3 scripts/backfill_demo_analytics.py [material.duckdb 路径，默认 demo_data/runtime/material.duckdb]
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "demo_data" / "runtime" / "material.duckdb"


def _h(text: str, salt: str) -> int:
    """稳定哈希，保证同一物资每次得到相同结果（幂等）。"""
    return int(hashlib.md5(f"{text}{salt}".encode("utf-8")).hexdigest(), 16)


def _backfill_region(con: duckdb.DuckDBPyConnection) -> int:
    """从存放位置推导区域：溪洛渡 / 向家坝 / 成都 / 其他。"""
    cur = con.execute(
        """
        UPDATE fact_inventory SET region = CASE
          WHEN location LIKE '%溪洛渡%' OR location LIKE '%溪右%'
               OR location LIKE '%溪左%' OR location LIKE '%溪控%' THEN '溪洛渡'
          WHEN location LIKE '%向家坝%' THEN '向家坝'
          WHEN location LIKE '%成都%' OR location LIKE '%三峡%' THEN '成都'
          ELSE '其他'
        END
        """
    )
    return cur.fetchone()  # type: ignore[return-value]


def _backfill_min_qty(con: duckdb.DuckDBPyConnection) -> int:
    """合成最低库存：无库存行必低库存，其余按哈希制造约 1/8 的低库存项。"""
    rows = con.execute(
        "SELECT inventory_id, material_id, COALESCE(stock_qty, 0) "
        "FROM fact_inventory WHERE min_qty IS NULL"
    ).fetchall()
    n = 0
    for inventory_id, material_id, stock in rows:
        h1 = _h(str(material_id), "min-qty")
        if stock <= 0:
            # 无库存：最低库存 5~25，真实低库存
            min_qty = round(5 + (h1 % 40) / 2, 2)
        elif h1 % 8 == 0:
            # 约 1/8 项：最低库存高于现有库存 10%~60%
            min_qty = round(stock * (1.1 + (h1 % 50) / 100), 2)
        else:
            # 健康项：最低库存约为现有库存的 40%~80%
            min_qty = round(stock * (0.4 + (h1 % 40) / 100), 2)
        con.execute(
            "UPDATE fact_inventory SET min_qty = ? WHERE inventory_id = ?",
            [min_qty, inventory_id],
        )
        n += 1
    return n


_COMPANIES = ["CTGCY"] * 60 + ["CYPC"] * 25 + ["CTGYC"] * 15
_DOMAINS = ["TDCD"] * 45 + ["TD"] * 25 + ["TDKD"] * 20 + ["GZB"] * 10
# (年份, 权重)，参考真实资产购买年份集中于 2022 附近
_YEARS = [
    (2015, 2), (2016, 3), (2017, 3), (2018, 4), (2019, 8), (2020, 12),
    (2021, 12), (2022, 25), (2023, 15), (2024, 10), (2025, 6),
]
_YEAR_TOTAL = sum(w for _, w in _YEARS)
_REGION_LOCATION = {"TDCD": "成都三峡大厦", "TD": "向家坝", "TDKD": "溪洛渡", "GZB": "葛洲坝"}


def _pick_year(v: int) -> int:
    r = v % _YEAR_TOTAL
    for year, w in _YEARS:
        if r < w:
            return year
        r -= w
    return _YEARS[-1][0]


def _backfill_asset(con: duckdb.DuckDBPyConnection) -> int:
    """合成资产清查演示行：公司/区域/购买年份分布可出图。"""
    # 幂等：先清掉旧演示行
    con.execute("DELETE FROM fact_asset WHERE row_key LIKE 'asset-demo-%'")
    mats = con.execute(
        "SELECT d.material_id, d.material_code, d.material_name, d.spec, d.unit "
        "FROM dim_material d "
        "WHERE d.material_id IN (SELECT DISTINCT material_id FROM fact_inventory) "
        "ORDER BY d.material_id LIMIT 120"
    ).fetchall()
    if not mats:
        return 0
    n = 0
    for i, (material_id, material_code, material_name, spec, unit) in enumerate(mats):
        h1 = _h(str(material_id), "asset")
        year = _pick_year(h1)
        code = f"ZC-{year}-{i + 1:04d}"
        company = _COMPANIES[h1 % len(_COMPANIES)]
        domain = _DOMAINS[(h1 >> 4) % len(_DOMAINS)]
        name = f"{material_name or '未命名物资'}{'·' + spec if spec else ''}"
        status = "正常" if h1 % 10 else "有问题"
        check_result = "账实相符" if h1 % 10 else "账实不符"
        month = 1 + h1 % 12
        day = 1 + (h1 >> 8) % 28
        con.execute(
            "INSERT INTO fact_asset ("
            "asset_code, asset_name, row_key, company, domain, user_name, manager, "
            "location, purchase_date, status, check_result, material_code, asset_qty, "
            "unit, is_instrument, replace_cycle, check_cycle, consumption_plan, "
            "tool_source, asset_quota_qty, remark, source_file, color_flag, "
            "source_sheet, source_release_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                code,
                name,
                f"asset-demo-{i + 1}",
                company,
                domain,
                None,
                None,
                _REGION_LOCATION.get(domain, "成都"),
                f"{year}-{month:02d}-{day:02d} 00:00:00",
                status,
                check_result,
                material_code,
                float(1 + h1 % 5),
                unit or "个",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "通信部成都分部资产清查汇总表（演示样例）.xlsx",
                None,
                "资产清查（成溪向）",
                None,
            ],
        )
        n += 1
    return n


def backfill_demo_analytics(db_path: str | Path) -> dict[str, int]:
    """对指定演示库执行补齐，返回各板块影响行数。"""
    db = Path(db_path)
    if not db.exists():
        raise FileNotFoundError(f"演示库不存在: {db}")
    con = duckdb.connect(str(db))
    try:
        # region：无条件重算（由 location 确定性推导）
        region_n = _backfill_region(con)[0]
        min_n = _backfill_min_qty(con)
        asset_n = _backfill_asset(con)
    finally:
        con.close()
    return {"region": int(region_n), "min_qty": min_n, "asset": asset_n}


def main() -> int:
    db = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    print("backfill db:", db)
    summary = backfill_demo_analytics(db)
    print("backfill summary:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
