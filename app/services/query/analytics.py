# -*- coding: utf-8 -*-
"""分析面只读聚合（question/03 UI-1）：治理中心流水分析 / 首页迷你趋势数据源。

出入库按月趋势与 Top 物资支持按物资种类、年份筛选（参数占位符绑定）。
L1/L2/L3 占比仍为全量解析口径，不绑定业务筛选。
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.repositories import biz_conn
from app.services.query.materials_standardized import STANDARD_CATEGORIES, parse_categories

_YEAR_RE = re.compile(r"^\d{4}$")


def parse_year(raw: str | None) -> str | None:
    s = (raw or "").strip()
    return s if _YEAR_RE.fullmatch(s) else None


def _flow_where(categories: list[str], year: str | None) -> tuple[str, list[Any]]:
    clauses = ["f.flow_date IS NOT NULL"]
    params: list[Any] = []
    if year:
        clauses.append("substr(CAST(f.flow_date AS VARCHAR), 1, 4) = ?")
        params.append(year)
    if categories:
        ph = ", ".join("?" * len(categories))
        clauses.append(f"(f.source_sheet IN ({ph}) OR d.category IN ({ph}))")
        params.extend(categories)
        params.extend(categories)
    return " AND ".join(clauses), params


def _fetch_records(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    con = biz_conn()
    try:
        df = con.execute(sql, params).fetchdf() if params else con.execute(sql).fetchdf()
    finally:
        con.close()
    if df is None or len(df) == 0:
        return []
    return json.loads(df.to_json(orient="records"))


def flow_filters() -> dict[str, Any]:
    """趋势分析筛选项：标准物资种类 + 流水中出现的年份。"""
    con = biz_conn()
    try:
        df = con.execute(
            "SELECT DISTINCT substr(CAST(flow_date AS VARCHAR), 1, 4) AS year "
            "FROM fact_stock_flow WHERE flow_date IS NOT NULL"
        ).fetchdf()
    finally:
        con.close()
    years: list[str] = []
    if df is not None and len(df):
        seen: set[str] = set()
        for raw in df["year"].tolist():
            y = parse_year(None if raw is None else str(raw))
            if y and y not in seen:
                seen.add(y)
                years.append(y)
        years.sort(reverse=True)
    return {"categories": list(STANDARD_CATEGORIES), "years": years}


def _standard_cats(raw: str | None) -> list[str]:
    """只保留标准物资种类，未知分类忽略（与 /materials/standardized 一致）。"""
    return [c for c in parse_categories(raw) if c in STANDARD_CATEGORIES]


def flow_monthly(categories: str | None = None, year: str | None = None) -> dict[str, Any]:
    """出入库按月 IN/OUT 趋势（与 ReportsView rpt_flow_monthly 同口径，可筛选）。"""
    cats = _standard_cats(categories)
    yr = parse_year(year)
    where_sql, params = _flow_where(cats, yr)
    rows = _fetch_records(
        "SELECT substr(CAST(f.flow_date AS VARCHAR), 1, 7) AS month, f.flow_type, "
        "ROUND(SUM(f.quantity), 2) AS qty "
        "FROM fact_stock_flow f "
        "LEFT JOIN dim_material d ON f.material_id = d.material_id "
        f"WHERE {where_sql} "
        "GROUP BY 1, 2 ORDER BY 1",
        params,
    )
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
        "filters": {"categories": cats, "year": yr},
    }


def flow_top(
    limit: int = 10,
    categories: str | None = None,
    year: str | None = None,
) -> dict[str, Any]:
    """Top 物资流水（IN/OUT 分别计数与数量，UI-1 柱状图）。

    口径：先按物资总出入库量（SUM(quantity)）选出 TopN 物资，再返回这些
    物资的 IN/OUT 分组行——避免旧实现"按单条 flow_type 行 LIMIT"导致
    IN/OUT 对比被截断。内部按 material_id 聚合（对齐不依赖中文名），
    左连接 dim_material，返回 asset_code / material_name / spec /
    display_name 供前端中文展示。可按物资种类、年份筛选。
    """
    limit = max(1, min(int(limit), 50))
    cats = _standard_cats(categories)
    yr = parse_year(year)
    where_sql, params = _flow_where(cats, yr)
    sql = (
        "WITH filtered AS ("
        "  SELECT f.material_id, f.flow_type, f.quantity "
        "  FROM fact_stock_flow f "
        "  LEFT JOIN dim_material d ON f.material_id = d.material_id "
        f"  WHERE {where_sql}"
        "), "
        "top_ids AS ("
        "  SELECT material_id FROM filtered "
        "  GROUP BY material_id ORDER BY SUM(quantity) DESC LIMIT ?"
        ") "
        "SELECT f.material_id, "
        "COALESCE(d.material_code, f.material_id) AS asset_code, "
        "d.material_name, d.spec, f.flow_type, f.n, f.qty "
        "FROM ("
        "  SELECT material_id, flow_type, COUNT(*) AS n, ROUND(SUM(quantity), 2) AS qty "
        "  FROM filtered "
        "  WHERE material_id IN (SELECT material_id FROM top_ids) "
        "  GROUP BY 1, 2"
        ") f "
        "LEFT JOIN dim_material d USING (material_id) "
        "ORDER BY f.qty DESC"
    )
    items: list[dict[str, Any]] = []
    for r in _fetch_records(sql, [*params, limit]):
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
    return {
        "limit": limit,
        "items": items,
        "filters": {"categories": cats, "year": yr},
    }


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
