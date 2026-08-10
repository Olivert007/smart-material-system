# -*- coding: utf-8 -*-
"""Report definition + run artifacts (roadmap §5 / P1-5)."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app import config
from app.repositories import meta_tx
from app.services import csv_safe
from app.services.sql_guard import validate_readonly_sql


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


# P2 分析面预置报表（question/03 建议 5 / UI-5）：启动幂等 upsert，
# 依赖同源只读 SQL（sql_guard 校验），cron_expr 为「分 时 * * *」每日执行
SEED_REPORTS: list[dict[str, Any]] = [
    {
        "report_id": "rpt_flow_monthly",
        "name": "出入库按月趋势",
        "query_sql": (
            "SELECT substr(flow_date, 1, 7) AS month, flow_type, "
            "ROUND(SUM(quantity), 2) AS qty "
            "FROM fact_stock_flow WHERE flow_date IS NOT NULL "
            "GROUP BY 1, 2 ORDER BY 1"
        ),
        "cron_expr": "0 8 * * *",
    },
    {
        "report_id": "rpt_flow_top_material",
        "name": "Top 物资流水",
        "query_sql": (
            "SELECT material_id, flow_type, COUNT(*) AS n, ROUND(SUM(quantity), 2) AS qty "
            "FROM fact_stock_flow GROUP BY 1, 2 ORDER BY qty DESC LIMIT 50"
        ),
        "cron_expr": "0 9 * * *",
    },
    {
        "report_id": "rpt_inv_by_category",
        "name": "库存按类别汇总",
        "query_sql": (
            "SELECT category, COUNT(*) AS materials, ROUND(SUM(stock_qty), 0) AS stock_qty, "
            "ROUND(SUM(COALESCE(stock_value, 0)), 2) AS stock_value "
            "FROM fact_inventory GROUP BY category ORDER BY stock_qty DESC"
        ),
        "cron_expr": "0 8 * * *",
    },
    {
        "report_id": "rpt_inv_filtered",
        "name": "库存筛选（带参数示例）",
        "query_sql": (
            "SELECT category, material_id, unit, stock_qty FROM fact_inventory "
            "WHERE category=${category} AND stock_qty >= ${min_qty} "
            "ORDER BY stock_qty DESC"
        ),
        "cron_expr": "",
        "params": [
            {"name": "category", "label": "物资类别", "type": "text"},
            {"name": "min_qty", "label": "最低库存量", "type": "number"},
        ],
    },
    # T7: ledger-export-plan §7 台账 4-sheet 导出报表（LD-5 固定列序；2026-08-10）。
    # 按 source_sheet 过滤（sheet 标记 T3 起落库），流水聚合列经 fact_stock_flow 子查询。
    {
        "report_id": "rpt_ledger_weihu",
        "name": "台账·维护材料",
        "query_sql": (
            "SELECT m.material_name, m.spec, i.stock_qty, i.opening_qty, i.quota_qty, "
            "i.min_qty, i.unit, i.location, i.custodian, i.belong_system, i.project_name, "
            "i.material_source, i.group_code, i.remark, "
            "fl.qty_in, fl.qty_out, fl.flow_times "
            "FROM fact_inventory i "
            "LEFT JOIN dim_material m USING (material_id) "
            "LEFT JOIN (SELECT material_id, "
            "  ROUND(SUM(CASE WHEN flow_type='IN' THEN COALESCE(quantity,0) ELSE 0 END),2) AS qty_in, "
            "  ROUND(SUM(CASE WHEN flow_type='OUT' THEN COALESCE(quantity,0) ELSE 0 END),2) AS qty_out, "
            "  COUNT(*) AS flow_times "
            "  FROM fact_stock_flow WHERE source_sheet='维护材料' GROUP BY material_id) fl "
            "ON fl.material_id = i.material_id "
            "WHERE i.source_sheet='维护材料' ORDER BY m.material_name"
        ),
        "cron_expr": "",
    },
    {
        "report_id": "rpt_ledger_beipin",
        "name": "台账·备品备件",
        "query_sql": (
            "SELECT m.material_name, m.spec, i.stock_qty, i.opening_qty, i.quota_qty, "
            "i.min_qty, i.unit, i.location, i.custodian, i.belong_system, i.project_name, "
            "i.material_source, i.group_code, i.remark, "
            "fl.qty_in, fl.qty_out, fl.flow_times "
            "FROM fact_inventory i "
            "LEFT JOIN dim_material m USING (material_id) "
            "LEFT JOIN (SELECT material_id, "
            "  ROUND(SUM(CASE WHEN flow_type='IN' THEN COALESCE(quantity,0) ELSE 0 END),2) AS qty_in, "
            "  ROUND(SUM(CASE WHEN flow_type='OUT' THEN COALESCE(quantity,0) ELSE 0 END),2) AS qty_out, "
            "  COUNT(*) AS flow_times "
            "  FROM fact_stock_flow WHERE source_sheet='备品备件' GROUP BY material_id) fl "
            "ON fl.material_id = i.material_id "
            "WHERE i.source_sheet='备品备件' ORDER BY m.material_name"
        ),
        "cron_expr": "",
    },
    {
        "report_id": "rpt_ledger_yjbm",
        "name": "台账·应急备汛物资",
        "query_sql": (
            "SELECT m.material_name, m.spec, i.stock_qty, i.opening_qty, i.quota_qty, "
            "i.min_qty, i.unit, i.location, i.custodian, i.belong_system, i.project_name, "
            "i.material_source, i.group_code, i.remark, "
            "fl.qty_in, fl.qty_out, fl.flow_times "
            "FROM fact_inventory i "
            "LEFT JOIN dim_material m USING (material_id) "
            "LEFT JOIN (SELECT material_id, "
            "  ROUND(SUM(CASE WHEN flow_type='IN' THEN COALESCE(quantity,0) ELSE 0 END),2) AS qty_in, "
            "  ROUND(SUM(CASE WHEN flow_type='OUT' THEN COALESCE(quantity,0) ELSE 0 END),2) AS qty_out, "
            "  COUNT(*) AS flow_times "
            "  FROM fact_stock_flow WHERE source_sheet='应急备汛物资' GROUP BY material_id) fl "
            "ON fl.material_id = i.material_id "
            "WHERE i.source_sheet='应急备汛物资' ORDER BY m.material_name"
        ),
        "cron_expr": "",
    },
    {
        "report_id": "rpt_ledger_gongju",
        "name": "台账·公用工器具",
        "query_sql": (
            "SELECT a.asset_code, a.asset_name, a.material_code, a.asset_qty, a.unit, "
            "a.replace_cycle, a.check_cycle, a.status, a.user_name, a.location, "
            "a.tool_source, a.asset_quota_qty, a.consumption_plan, a.remark "
            "FROM fact_asset a "
            "WHERE a.source_sheet='公用工器具' ORDER BY a.asset_code"
        ),
        "cron_expr": "",
    },
]


SEED_REPORT_IDS = frozenset(s["report_id"] for s in SEED_REPORTS)


def ensure_report_seed(*, actor: str = "system:seed") -> dict:
    """幂等 upsert 预置报表（UI-5 前置：ReportsView 首次打开即有 4 条种子报表）。"""
    created, skipped = 0, 0
    for s in SEED_REPORTS:
        with meta_tx() as con:
            row = con.execute(
                "SELECT report_id FROM report_definition WHERE report_id=?", [s["report_id"]]
            ).fetchone()
        if row:
            skipped += 1
            continue
        create_report(
            report_id=s["report_id"],
            name=s["name"],
            query_sql=s["query_sql"],
            actor=actor,
            cron_expr=s["cron_expr"],
            params=s.get("params"),
        )
        created += 1
    return {"ok": True, "created": created, "skipped": skipped, "ids": [s["report_id"] for s in SEED_REPORTS]}


def reports_dir() -> Path:
    p = Path(config.DATA) / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_reports() -> dict:
    with meta_tx() as con:
        rows = con.execute(
            "SELECT * FROM report_definition ORDER BY created_at DESC"
        ).fetchall()
    return {"total": len(rows), "items": [dict(r) for r in rows]}


def create_report(
    *,
    name: str,
    query_sql: str,
    actor: str,
    report_id: str | None = None,
    cron_expr: str = "",
    params: list | dict | None = None,
) -> dict:
    # ${name} 占位符先替换为字面量再过 AST 校验（渲染后值已在 run 时二次校验）
    guard = validate_readonly_sql(re.sub(r"\$\{([A-Za-z0-9_]+)\}", "'x'", query_sql))
    if not guard.ok:
        raise ValueError(guard.error or "unsafe sql")
    rid = (report_id or f"rpt_{_sid(10)}").strip()
    import json

    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO report_definition (
                report_id, name, query_sql, params_json, cron_expr, active, created_by
            ) VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(report_id) DO UPDATE SET
                name=excluded.name,
                query_sql=excluded.query_sql,
                params_json=excluded.params_json,
                cron_expr=excluded.cron_expr,
                created_by=excluded.created_by
            """,
            [
                rid,
                name,
                query_sql,
                json.dumps(params or {}, ensure_ascii=False),
                cron_expr or None,
                actor,
            ],
        )
    return {"ok": True, "report_id": rid, "name": name, "actor": actor}


_PARAM_VALUE_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fa5 .%]+$")


def _render_params(sql: str, params: dict) -> str:
    """将 SQL 中 ${name} 占位符替换为参数值（UI-4）。

    安全约束：值经白名单校验；字符串单引号包裹（转义内部单引号），
    数字/布尔原样替换；替换结果再走 sql_guard 只读校验。缺失占位符报错。
    """
    if "${" not in sql:
        return sql

    def _one(m: re.Match) -> str:
        name = m.group(1).strip()
        if name not in params:
            raise ValueError(f"missing param: {name}")
        v = params[name]
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, str):
            if v.strip() == "":
                return "''"
            if not _PARAM_VALUE_RE.fullmatch(v):
                raise ValueError(f"invalid param value: {name}")
            return "'" + v.replace("'", "''") + "'"
        raise ValueError(f"unsupported param type: {name}")

    return re.sub(r"\$\{([A-Za-z0-9_]+)\}", _one, sql)


def run_report(
    report_id: str, *, actor: str = "system", params: dict | None = None
) -> dict[str, Any]:
    import json
    from app.repositories import biz_conn
    from app.services import query as query_svc

    with meta_tx() as con:
        row = con.execute(
            "SELECT * FROM report_definition WHERE report_id=?", [report_id]
        ).fetchone()
        if not row:
            raise KeyError("report not found")
        if not int(row["active"] or 0):
            raise RuntimeError("report inactive")
        run_id = f"run_{_sid(12)}"
        con.execute(
            """
            INSERT INTO report_run (run_id, report_id, status, started_at)
            VALUES (?, ?, 'running', ?)
            """,
            [run_id, report_id, _now()],
        )
    try:
        # 参数化：${param} 占位替换（白名单），随后仍过 AST 只读校验
        sql = _render_params(row["query_sql"], params or {})
        guard = validate_readonly_sql(sql)
        if not guard.ok:
            raise ValueError(guard.error or "unsafe sql")
        result = query_svc.run_readonly_query(sql, allow_free=True, row_limit=None)
        data = result.get("data") or []
        df = pd.DataFrame(data)
        out_dir = reports_dir() / report_id
        out_dir.mkdir(parents=True, exist_ok=True)
        artifact = out_dir / f"{run_id}.parquet"
        df.to_parquet(artifact, index=False)
        csv_path = out_dir / f"{run_id}.csv"
        # csv-export-harden T1.2/T2.3: csv 产物加 BOM + 注入净化（parquet 保持原始值）
        csv_safe.sanitize_df(df).to_csv(csv_path, index=False, encoding="utf-8-sig")
        with meta_tx() as con:
            con.execute(
                """
                UPDATE report_run
                SET status='done', finished_at=?, artifact_path=?, row_count=?, error=NULL
                WHERE run_id=?
                """,
                [_now(), str(artifact), int(len(df)), run_id],
            )
            con.execute(
                """
                INSERT INTO write_audit (action, release_id, actor, detail_json)
                VALUES ('report_run', NULL, ?, ?)
                """,
                [
                    actor,
                    json.dumps(
                        {"report_id": report_id, "run_id": run_id, "rows": len(df)},
                        ensure_ascii=False,
                    ),
                ],
            )
        return {
            "ok": True,
            "run_id": run_id,
            "report_id": report_id,
            "status": "done",
            "row_count": int(len(df)),
            "artifact_path": str(artifact),
            "csv_path": str(csv_path),
            "actor": actor,
        }
    except Exception as e:
        with meta_tx() as con:
            con.execute(
                """
                UPDATE report_run
                SET status='failed', finished_at=?, error=?
                WHERE run_id=?
                """,
                [_now(), str(e)[:500], run_id],
            )
        raise


def get_run(run_id: str) -> dict:
    with meta_tx() as con:
        row = con.execute(
            "SELECT * FROM report_run WHERE run_id=?", [run_id]
        ).fetchone()
    if not row:
        raise KeyError("run not found")
    return dict(row)


def list_runs(report_id: str | None = None, *, limit: int = 50) -> dict:
    limit = max(1, min(int(limit), 200))
    with meta_tx() as con:
        if report_id:
            rows = con.execute(
                """
                SELECT * FROM report_run WHERE report_id=?
                ORDER BY started_at DESC LIMIT ?
                """,
                [report_id, limit],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM report_run ORDER BY started_at DESC LIMIT ?",
                [limit],
            ).fetchall()
    return {"total": len(rows), "items": [dict(r) for r in rows]}


def _parse_interval_minutes(cron_expr: str | None) -> int | None:
    """Support simple schedules: '5', 'every:5m', '*/5' (minutes), '0 8 * * *' (每日). Empty = manual only."""
    if not cron_expr:
        return None
    s = str(cron_expr).strip().lower()
    if not s:
        return None
    if s.isdigit():
        return max(1, int(s))
    if s.startswith("every:"):
        body = s[6:].strip().rstrip("m")
        if body.isdigit():
            return max(1, int(body))
    if s.startswith("*/") and s[2:].isdigit():
        return max(1, int(s[2:]))
    # 「分 时 * * *」每日执行（P2 种子报表格式）；不做精确到点，只取日间隔
    m = re.match(r"^(\d+)\s+(\d+)\s*\*\s*\*\s*\*$", s)
    if m:
        return 24 * 60
    return None


def claim_due_report() -> str | None:
    """Return one due report_id (no overlapping running run)."""
    now = datetime.now(timezone.utc)
    with meta_tx() as con:
        rows = con.execute(
            """
            SELECT report_id, cron_expr FROM report_definition
            WHERE active=1 AND cron_expr IS NOT NULL AND TRIM(cron_expr) != ''
            ORDER BY created_at ASC
            """
        ).fetchall()
        for r in rows:
            mins = _parse_interval_minutes(r["cron_expr"])
            if mins is None:
                continue
            rid = r["report_id"]
            running = con.execute(
                """
                SELECT 1 FROM report_run
                WHERE report_id=? AND status='running'
                LIMIT 1
                """,
                [rid],
            ).fetchone()
            if running:
                continue
            last = con.execute(
                """
                SELECT finished_at, started_at FROM report_run
                WHERE report_id=? AND status IN ('done','failed')
                ORDER BY COALESCE(finished_at, started_at) DESC
                LIMIT 1
                """,
                [rid],
            ).fetchone()
            if last:
                ts = last["finished_at"] or last["started_at"]
                try:
                    last_dt = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                except Exception:
                    last_dt = now
                if (now - last_dt).total_seconds() < mins * 60:
                    continue
            return rid
    return None


def process_due_report_once(*, actor: str = "system:cron") -> dict | None:
    rid = claim_due_report()
    if not rid:
        return None
    return run_report(rid, actor=actor)
