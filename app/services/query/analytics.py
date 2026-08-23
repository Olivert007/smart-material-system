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
    from app.services.govern.flow_gov import parse_stats

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


# ---------- 数据成果页·趋势分析：参考《通信部成都分部数据分析报告》的分类与展示 ----------
# 新增只读聚合（analysis report §2 资产清查 / §3-4 库存健康 / §5 需求 / §6 定额调整）：
# 与流水分析共用同一筛选语义（物资种类 + 年份，仅作用于流水口径），其余板块为全量概览。


def _fmt_display(name: str, spec: str | None = None, code: str | None = None) -> str:
    """组合中文展示名；空名或与编码相同时退化为中性占位，不暴露内部编号。"""
    n = (name or "").strip()
    s = (spec or "").strip()
    c = (code or "").strip()
    if n and s:
        return f"{n}·{s}"
    if n:
        return n
    return "未命名物资"


def flow_summary(categories: str | None = None, year: str | None = None) -> dict[str, Any]:
    """流水概览 KPI：总条数、入库/出库条数与数量、净变化、涉及物资数、日期范围。"""
    cats = _standard_cats(categories)
    yr = parse_year(year)
    where_sql, params = _flow_where(cats, yr)
    rows = _fetch_records(
        "SELECT flow_type, COUNT(*) AS n, ROUND(SUM(quantity), 2) AS qty "
        "FROM fact_stock_flow f "
        "LEFT JOIN dim_material d ON f.material_id = d.material_id "
        f"WHERE {where_sql} GROUP BY 1",
        params,
    )
    meta = _fetch_records(
        "SELECT COUNT(*) AS total, COUNT(DISTINCT f.material_id) AS materials, "
        "MIN(f.flow_date) AS min_date, MAX(f.flow_date) AS max_date "
        "FROM fact_stock_flow f "
        "LEFT JOIN dim_material d ON f.material_id = d.material_id "
        f"WHERE {where_sql}",
        params,
    )
    in_qty = out_qty = 0.0
    in_n = out_n = 0
    for r in rows:
        if r.get("flow_type") == "IN":
            in_n = int(r.get("n") or 0)
            in_qty = float(r.get("qty") or 0)
        else:
            out_n = int(r.get("n") or 0)
            out_qty = float(r.get("qty") or 0)
    m = meta[0] if meta else {}
    return {
        "total": int(m.get("total") or 0),
        "materials": int(m.get("materials") or 0),
        "min_date": m.get("min_date"),
        "max_date": m.get("max_date"),
        "in": {"count": in_n, "qty": in_qty},
        "out": {"count": out_n, "qty": out_qty},
        "net": round(in_qty - out_qty, 2),
        "filters": {"categories": cats, "year": yr},
    }


def inventory_health(top_n: int = 10) -> dict[str, Any]:
    """库存健康（报告 §3 台账 305-B + §4 溪洛渡概览）：类别/区域分布、低库存、超定额 TOP。"""
    n = max(1, min(int(top_n), 30))
    con = biz_conn()
    try:
        by_category = con.execute(
            "SELECT COALESCE(category, '(空)') AS name, COUNT(*) AS cnt, "
            "ROUND(SUM(COALESCE(stock_qty, 0)), 2) AS stock_qty "
            "FROM fact_inventory GROUP BY 1 ORDER BY cnt DESC LIMIT ?",
            [n],
        ).fetchall()
        by_region = con.execute(
            "SELECT COALESCE(region, '(空)') AS name, COUNT(*) AS cnt "
            "FROM fact_inventory GROUP BY 1 ORDER BY cnt DESC"
        ).fetchall()
        low_rows = con.execute(
            "SELECT i.material_id, d.material_name, d.spec, i.stock_qty, i.min_qty "
            "FROM fact_inventory i LEFT JOIN dim_material d USING (material_id) "
            "WHERE i.min_qty IS NOT NULL AND i.stock_qty < i.min_qty "
            "ORDER BY (i.min_qty - i.stock_qty) DESC LIMIT ?",
            [n],
        ).fetchall()
        low_total = con.execute(
            "SELECT COUNT(*) FROM fact_inventory "
            "WHERE min_qty IS NOT NULL AND stock_qty < min_qty"
        ).fetchone()[0]
        over_rows = con.execute(
            "SELECT i.material_id, d.material_name, d.spec, i.stock_qty, i.quota_qty "
            "FROM fact_inventory i LEFT JOIN dim_material d USING (material_id) "
            "WHERE i.quota_qty IS NOT NULL AND i.stock_qty > i.quota_qty "
            "ORDER BY (i.stock_qty - i.quota_qty) DESC LIMIT ?",
            [n],
        ).fetchall()
        over_total = con.execute(
            "SELECT COUNT(*) FROM fact_inventory "
            "WHERE quota_qty IS NOT NULL AND stock_qty > quota_qty"
        ).fetchone()[0]
        total = con.execute("SELECT COUNT(*) FROM fact_inventory").fetchone()[0]
        stock_qty_total = con.execute(
            "SELECT ROUND(SUM(COALESCE(stock_qty, 0)), 2) FROM fact_inventory"
        ).fetchone()[0]
    finally:
        con.close()
    return {
        "total": int(total),
        "stock_qty_total": float(stock_qty_total or 0),
        "by_category": [
            {"name": str(r[0]), "count": int(r[1]), "stock_qty": float(r[2] or 0)}
            for r in by_category
        ],
        "by_region": [{"name": str(r[0]), "count": int(r[1])} for r in by_region],
        "low_stock": {
            "count": int(low_total),
            "items": [
                {
                    "material_id": str(r[0]),
                    "display_name": _fmt_display(r[1], r[2], r[0]),
                    "stock_qty": float(r[3] or 0),
                    "min_qty": float(r[4] or 0),
                }
                for r in low_rows
            ],
        },
        "over_quota": {
            "count": int(over_total),
            "items": [
                {
                    "material_id": str(r[0]),
                    "display_name": _fmt_display(r[1], r[2], r[0]),
                    "stock_qty": float(r[3] or 0),
                    "quota_qty": float(r[4] or 0),
                }
                for r in over_rows
            ],
        },
    }


def asset_overview(limit: int = 12) -> dict[str, Any]:
    """资产清查（报告 §2 资产清查分析）：状态/公司/区域/购买年份分布、盘点问题 TOP。"""
    n = max(1, min(int(limit), 30))
    con = biz_conn()
    try:
        by_status = con.execute(
            "SELECT COALESCE(status, '(空)') AS name, COUNT(*) AS cnt "
            "FROM fact_asset GROUP BY 1 ORDER BY cnt DESC"
        ).fetchall()
        by_company = con.execute(
            "SELECT COALESCE(company, '(空)') AS name, COUNT(*) AS cnt "
            "FROM fact_asset GROUP BY 1 ORDER BY cnt DESC"
        ).fetchall()
        by_domain = con.execute(
            "SELECT COALESCE(domain, '(空)') AS name, COUNT(*) AS cnt "
            "FROM fact_asset GROUP BY 1 ORDER BY cnt DESC"
        ).fetchall()
        by_year = con.execute(
            "SELECT substr(purchase_date, 1, 4) AS name, COUNT(*) AS cnt "
            "FROM fact_asset "
            "WHERE purchase_date IS NOT NULL AND purchase_date != '' "
            "GROUP BY 1 ORDER BY 1"
        ).fetchall()
        problem = con.execute(
            "SELECT COALESCE(check_result, '未填写') AS name, COUNT(*) AS cnt "
            "FROM fact_asset WHERE status='有问题' "
            "GROUP BY 1 ORDER BY cnt DESC LIMIT ?",
            [n],
        ).fetchall()
        total = con.execute("SELECT COUNT(*) FROM fact_asset").fetchone()[0]
        company_cnt = con.execute(
            "SELECT COUNT(DISTINCT company) FROM fact_asset "
            "WHERE company IS NOT NULL AND company != ''"
        ).fetchone()[0]
        domain_cnt = con.execute(
            "SELECT COUNT(DISTINCT domain) FROM fact_asset "
            "WHERE domain IS NOT NULL AND domain != ''"
        ).fetchone()[0]
    finally:
        con.close()
    years = [r for r in by_year if r[0] is not None]
    return {
        "total": int(total),
        "company_count": int(company_cnt),
        "domain_count": int(domain_cnt),
        "by_status": [{"name": str(r[0]), "count": int(r[1])} for r in by_status],
        "by_company": [{"name": str(r[0]), "count": int(r[1])} for r in by_company],
        "by_domain": [{"name": str(r[0]), "count": int(r[1])} for r in by_domain],
        "by_year": [
            {"name": str(r[0]), "count": int(r[1])}
            for r in years
            if str(r[0]).isdigit()
        ],
        "problem_top": [{"name": str(r[0]), "count": int(r[1])} for r in problem],
    }


def demand_overview(top_n: int = 10) -> dict[str, Any]:
    """需求（报告 §3 维护材料需求统计）：按需求期间汇总 + 需求物资 TOP。"""
    n = max(1, min(int(top_n), 30))
    con = biz_conn()
    try:
        rows = con.execute(
            "SELECT COALESCE(demand_period, '(未填写)') AS name, COUNT(*) AS cnt, "
            "ROUND(SUM(COALESCE(quantity, 0)), 2) AS qty "
            "FROM fact_demand GROUP BY 1 ORDER BY 1"
        ).fetchall()
        top = con.execute(
            "SELECT d.material_id, m.material_name, m.spec, "
            "COUNT(*) AS cnt, ROUND(SUM(COALESCE(d.quantity, 0)), 2) AS qty "
            "FROM fact_demand d LEFT JOIN dim_material m USING (material_id) "
            "GROUP BY 1, 2, 3 ORDER BY qty DESC LIMIT ?",
            [n],
        ).fetchall()
        total = con.execute("SELECT COUNT(*) FROM fact_demand").fetchone()[0]
        qty = con.execute("SELECT ROUND(SUM(COALESCE(quantity, 0)), 2) FROM fact_demand").fetchone()[0]
        materials = con.execute(
            "SELECT COUNT(DISTINCT material_id) FROM fact_demand"
        ).fetchone()[0]
    finally:
        con.close()
    return {
        "total": int(total),
        "quantity": float(qty or 0),
        "materials": int(materials),
        "by_period": [{"name": str(r[0]), "count": int(r[1]), "qty": float(r[2] or 0)} for r in rows],
        "top": [
            {
                "material_id": str(r[0]),
                "display_name": _fmt_display(r[1], r[2], r[0]),
                "count": int(r[3]),
                "qty": float(r[4] or 0),
            }
            for r in top
        ],
    }


def quota_overview(limit: int = 10) -> dict[str, Any]:
    """定额调整（报告 §6 备品备件定额调整清单）：调整类型分布 + 调整项 TOP。"""
    n = max(1, min(int(limit), 30))
    con = biz_conn()
    try:
        by_type = con.execute(
            "SELECT COALESCE(adjust_type, '(空)') AS name, COUNT(*) AS cnt "
            "FROM fact_quota_adjust GROUP BY 1 ORDER BY cnt DESC"
        ).fetchall()
        top = con.execute(
            "SELECT q.material_id, d.material_name, d.spec, COUNT(*) AS cnt, "
            "ROUND(SUM(COALESCE(q.verified_quota, 0)), 2) AS qty "
            "FROM fact_quota_adjust q LEFT JOIN dim_material d USING (material_id) "
            "GROUP BY 1, 2, 3 ORDER BY cnt DESC LIMIT ?",
            [n],
        ).fetchall()
        total = con.execute("SELECT COUNT(*) FROM fact_quota_adjust").fetchone()[0]
    finally:
        con.close()
    return {
        "total": int(total),
        "by_type": [{"name": str(r[0]), "count": int(r[1])} for r in by_type],
        "top": [
            {
                "material_id": str(r[0]),
                "display_name": _fmt_display(r[1], r[2], r[0]),
                "count": int(r[3]),
                "verified_qty": float(r[4] or 0),
            }
            for r in top
        ],
    }
