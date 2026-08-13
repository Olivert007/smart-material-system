# -*- coding: utf-8 -*-
"""分析面只读聚合（question/03 UI-1）：治理中心流水分析 / 首页迷你趋势数据源。

口径与 seed_reports 的 rpt_flow_monthly / rpt_flow_top_material 一致，
便于 ReportsView 与治理中心图表同口径互验；统一走 query.run_readonly_query
（AST 只读校验 + fetchdf 结构化返回）。
"""
from __future__ import annotations

from typing import Any

from app import config

_MONTHLY_SQL = (
    "SELECT substr(flow_date, 1, 7) AS month, flow_type, "
    "ROUND(SUM(quantity), 2) AS qty "
    "FROM fact_stock_flow WHERE flow_date IS NOT NULL "
    "GROUP BY 1, 2 ORDER BY 1"
)
_TOP_SQL = (
    "SELECT f.material_id, "
    "COALESCE(d.material_code, f.material_id) AS asset_code, "
    "d.material_name, d.spec, f.flow_type, f.n, f.qty "
    "FROM ("
    "  SELECT material_id, flow_type, COUNT(*) AS n, ROUND(SUM(quantity), 2) AS qty "
    "  FROM fact_stock_flow GROUP BY 1, 2"
    ") f "
    "LEFT JOIN dim_material d USING (material_id) "
    "ORDER BY f.qty DESC LIMIT {limit}"
)


def _run(sql: str) -> list[dict[str, Any]]:
    from app.services import query as query_svc

    result = query_svc.run_readonly_query(sql, allow_free=True, row_limit=config.QUERY_ROW_LIMIT)
    return result.get("data") or []


def flow_monthly() -> dict[str, Any]:
    """出入库按月 IN/OUT 趋势（与 ReportsView rpt_flow_monthly 同口径）。"""
    rows = _run(_MONTHLY_SQL)
    months: list[str] = []
    by_month: dict[str, dict[str, float]] = {}
    for r in rows:
        month = str(r.get("month") or "")
        ftype = str(r.get("flow_type") or "?")
        qty = float(r.get("qty") or 0)
        if month not in by_month:
            by_month[month] = {}
            months.append(month)
        by_month[month][ftype] = by_month[month].get(ftype, 0.0) + qty
    return {
        "items": rows,
        "months": months,
        "in": [by_month[m].get("IN", 0.0) for m in months],
        "out": [by_month[m].get("OUT", 0.0) for m in months],
    }


def flow_top(limit: int = 10) -> dict[str, Any]:
    """Top 物资流水（IN/OUT 分别计数与数量，UI-1 柱状图）。

    按内部 material_id 聚合（对齐不依赖中文名），左连接 dim_material，
    返回 asset_code / material_name / spec / display_name 供前端中文展示。
    """
    limit = max(1, min(int(limit), 50))
    items: list[dict[str, Any]] = []
    for r in _run(_TOP_SQL.format(limit=limit)):
        d = dict(r)
        mid = str(d.get("material_id") or "")
        code = str(d.get("asset_code") or "").strip() or mid
        name = str(d.get("material_name") or "").strip()
        spec = str(d.get("spec") or "").strip()
        if name and spec:
            display = f"{name}·{spec}"
        elif name:
            display = name
        else:
            display = code
        d["asset_code"] = code
        d["display_name"] = display
        items.append(d)
    return {"limit": limit, "items": items}


def flow_level_ratio() -> dict[str, Any]:
    """L1/L2/L3 占比（与 /govern/flow/stats published_by_level 同源）。"""
    from app.services.flow_gov import parse_stats

    stats = parse_stats()
    levels = stats.get("published_by_level") or {}
    total = int(stats.get("published_total") or 0)
    items = [
        {
            "name": lvl,
            "value": int(cnt),
            "ratio": round(int(cnt) / total, 4) if total else None,
        }
        for lvl, cnt in sorted(levels.items())
    ]
    return {"total": total, "items": items}
