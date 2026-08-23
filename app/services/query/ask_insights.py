# -*- coding: utf-8 -*-
"""Ask assistant insights: data-driven recommendations and empty-result guidance."""
from __future__ import annotations

import re
from typing import Any

from app.repositories import biz_conn, meta_conn

_BASE_METRIC_QUESTIONS = [
    "库存总量是多少",
    "库存表有多少行",
    "资产台数有多少",
    "需求总量是多少",
]

_INVENTORY_QUESTIONS = [
    "超定额物资有多少",
    "低于最低库存的物资有多少",
    "呆滞料有多少行",
    "零库存物资有多少",
    "缺少库位的库存有多少",
]

_FLOW_QUESTIONS = [
    "入库合计是多少",
    "出库合计是多少",
]

_ASSET_QUESTIONS = [
    "缺少保管人的资产有多少",
]

_COMPLEX_QUESTIONS = [
    "按库位统计库存记录数，取前10",
    "按类别统计库存量",
]


def _table_counts() -> dict[str, int]:
    tables = (
        "dim_material",
        "fact_inventory",
        "fact_asset",
        "fact_demand",
        "fact_stock_flow",
    )
    con = biz_conn()
    out: dict[str, int] = {}
    try:
        for t in tables:
            try:
                out[t] = int(con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
            except Exception:
                out[t] = 0
    finally:
        con.close()
    return out


def _has_recent_files() -> bool:
    con = meta_conn()
    try:
        row = con.execute("SELECT COUNT(*) AS c FROM file_batch").fetchone()
        return int(row["c"] if row else 0) > 0
    except Exception:
        return False
    finally:
        con.close()


def recommend_questions(*, model_available: bool = True) -> dict[str, Any]:
    """Data-aware recommended questions for the ask assistant (docs/17 §3.1 P0)."""
    counts = _table_counts()
    inv = counts.get("fact_inventory", 0)
    flow = counts.get("fact_stock_flow", 0)
    asset = counts.get("fact_asset", 0)
    demand = counts.get("fact_demand", 0)
    has_any = inv > 0 or flow > 0 or asset > 0 or demand > 0

    if not has_any and not _has_recent_files():
        return {
            "questions": [],
            "hint": "尚未接入数据，请先在「数据接入」上传库存、流水或资产文件。",
            "data_state": "no_data",
        }

    if not has_any and _has_recent_files():
        return {
            "questions": _BASE_METRIC_QUESTIONS[:3],
            "hint": "文件已上传但可用候选数据为空，可先问指标类问题，或到「数据规整」处理待办。",
            "data_state": "files_only",
        }

    questions: list[str] = []
    if inv > 0:
        questions.extend(_BASE_METRIC_QUESTIONS[:2])
        questions.extend(_INVENTORY_QUESTIONS)
    if demand > 0:
        questions.append("需求总量是多少")
    if asset > 0:
        questions.append("资产台数有多少")
        questions.extend(_ASSET_QUESTIONS)
    if flow > 0:
        questions.extend(_FLOW_QUESTIONS)
    if not questions:
        questions = list(_BASE_METRIC_QUESTIONS)

    if model_available:
        if inv > 0:
            questions.extend(_COMPLEX_QUESTIONS[:2])
    else:
        questions = [q for q in questions if q in _BASE_METRIC_QUESTIONS + _INVENTORY_QUESTIONS + _FLOW_QUESTIONS + _ASSET_QUESTIONS]

    # dedupe preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            deduped.append(q)

    hint = None
    if not model_available:
        hint = "本地模型离线：以下指标类问题可直接点击提问；分组统计需启动模型。"

    return {
        "questions": deduped[:10],
        "hint": hint,
        "data_state": "has_data",
        "tables": counts,
    }


_DEGRADED_EXAMPLES = [
    "库存总量是多少",
    "库存表有多少行",
    "超定额物资有多少",
    "资产台数有多少",
    "入库合计是多少",
]


def degraded_suggested_examples() -> list[str]:
    return list(_DEGRADED_EXAMPLES)


_KEYWORD_NEXT: list[tuple[re.Pattern[str], list[str]]] = [
    (
        re.compile(r"库存|库位|定额|呆滞|零库存"),
        ["超定额物资有多少", "呆滞料有多少行", "按库位统计库存记录数，取前10"],
    ),
    (
        re.compile(r"流水|入库|出库"),
        ["入库合计是多少", "出库合计是多少"],
    ),
    (
        re.compile(r"资产|保管人"),
        ["资产台数有多少", "缺少保管人的资产有多少"],
    ),
    (
        re.compile(r"需求"),
        ["需求总量是多少"],
    ),
]


def empty_result_insight(
    *,
    question: str,
    sql: str | None = None,
    source: str | None = None,
    metric_id: str | None = None,
) -> dict[str, Any]:
    """Guidance when ask returns zero rows or NULL aggregate (docs/17 §3.4 P0)."""
    q = (question or "").strip()
    reasons: list[str] = []
    suggested_next: list[str] = []

    if source == "metric_template" and metric_id:
        # definition_sql 带 CASE WHEN … THEN NULL 守卫（如 INV_QTY_TOTAL 多计量单位
        # 不可加总）时，NULL 是口径刻意返回，不是无数据，措辞需区分。
        if sql and re.search(r"THEN\s+NULL", sql or "", re.IGNORECASE):
            reasons.append(
                "该指标口径要求计量单位统一；当前数据存在多种计量单位，跨单位不可加总，故显示 —（并非无数据）。"
            )
        else:
            reasons.append("当前口径下没有符合条件的记录，或相关字段尚未填报。")
        if metric_id.startswith("INV_"):
            suggested_next.extend(
                ["库存表有多少行", "库存总量是多少", "超定额物资有多少"]
            )
        elif metric_id.startswith("FLOW_"):
            suggested_next.extend(["入库合计是多少", "出库合计是多少"])
        elif metric_id.startswith("ASSET_"):
            suggested_next.append("资产台数有多少")
        elif metric_id.startswith("DEMAND_"):
            suggested_next.append("需求总量是多少")
    else:
        reasons.append("查询未命中任何数据行。")
        if sql and re.search(r"(?i)\bwhere\b", sql or ""):
            reasons.append("可能筛选条件过严，可尝试放宽关键词或去掉部分条件。")
        else:
            reasons.append("可能表中暂无相关数据，或问法与现有字段口径不一致。")
        for pat, picks in _KEYWORD_NEXT:
            if pat.search(q):
                suggested_next.extend(picks)
                break

    if not suggested_next:
        suggested_next = list(_BASE_METRIC_QUESTIONS[:4])

    seen: set[str] = set()
    deduped: list[str] = []
    for s in suggested_next:
        if s != q and s not in seen:
            seen.add(s)
            deduped.append(s)

    return {
        "empty_reason": "；".join(reasons),
        "suggested_next": deduped[:4],
    }
