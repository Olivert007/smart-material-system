# -*- coding: utf-8 -*-
"""上传完成后的业务结论（optv1/04 数据接入）。

把技术状态翻译成业务结论：可进入规整 / 需字段处理 / 需结构确认 / 无法接入。
结论只做展示，不改变任何状态。
"""
from __future__ import annotations

from typing import Any

# 结构类问题：需要人工确认 Sheet/区域/列映射结构
STRUCTURE_CODES = {
    "NO_SHEETS",
    "NO_COLUMNS",
    "REGION_BOUNDS",
    "PROFILE_FAILED",
    "SKIP_ROLE",
    "SHEET_ROLE_UNKNOWN",
    "PLAN_FAILED",
    "STAGE_FAILED",
}

# 字段/质量类问题：需要处理字段映射、缺失必填、异常值等
FIELD_CODES = {
    "REQUIRED_UNMAPPED",
    "MISSING_REQUIRED",
    "EMPTY_ROW",
    "DUPLICATE_PK",
    "QTY_YEAR_LIKE",
    "QTY_NON_NUMERIC",
    "QTY_NEGATIVE",
    "UNKNOWN_HEADER",
    "MONEY_COLS_MISSING",
    "QUALITY_BLOCKING",
    "QUALITY_WARN",
    "QUALITY_FAILED",
    "MAP_PENDING",
    "MAP_ENQUEUE_FAILED",
    "MISSING_COL",
    "REQUIRED",
}


def _collect_codes(bundle: dict[str, Any]) -> list[str]:
    codes: list[str] = []

    analyze = bundle.get("analyze") or {}
    analyze_payload = analyze.get("analyze") or analyze
    for c in analyze_payload.get("codes") or []:
        if c not in codes:
            codes.append(str(c))

    quality = bundle.get("quality") or {}
    q = quality.get("quality") or {}
    if q.get("blocking") and "QUALITY_BLOCKING" not in codes:
        codes.append("QUALITY_BLOCKING")
    counts = q.get("issue_counts") or {}
    for key, val in (counts or {}).items():
        if val:
            c = str(key).upper()
            if c not in codes:
                codes.append(c)
    for issue in q.get("issues_sample") or []:
        c = issue.get("code")
        if c and c not in codes:
            codes.append(str(c))

    plan = bundle.get("plan") or {}
    gate = (plan.get("plan") or {}).get("gate") or {}
    for b in gate.get("blockers") or []:
        c = b.get("code")
        if c and c not in codes:
            codes.append(str(c))
    for w in gate.get("warnings") or []:
        c = w.get("code")
        if c and c not in codes:
            codes.append(str(c))

    return codes


def file_conclusion(file_id: str) -> dict[str, Any]:
    """返回 {file_id, status, conclusion, reason_codes, hint}。"""
    from app.services.intake_analyze import get_intake_bundle

    bundle = get_intake_bundle(file_id)
    fb = bundle.get("file") or {}
    status = str(fb.get("status") or "")

    base = {"file_id": file_id, "status": status, "reason_codes": []}
    if status == "failed":
        return {
            **base,
            "conclusion": "failed",
            "hint": "无法接入：解析失败，请检查文件格式或内容后重新上传。",
        }
    if status in ("uploaded", "pending", "processing"):
        return {
            **base,
            "conclusion": "parsing",
            "hint": "状态：原始。系统正在识别文件结构，完成后给出是否可进入规整的结论。",
        }
    if status == "released":
        return {
            **base,
            "conclusion": "published",
            "hint": "状态：已发布。已写入业务库（可用候选）；不等于正式发布报表。",
        }
    if status == "staged":
        return {
            **base,
            "conclusion": "standardized",
            "hint": "状态：规整。可继续确认或查看质量结果。",
        }

    # done / evidence_done → 从分析/质量/门禁结论归类
    codes = _collect_codes(bundle)
    structure = [c for c in codes if c in STRUCTURE_CODES]
    fields = [c for c in codes if c in FIELD_CODES]
    base["reason_codes"] = codes

    if structure:
        return {
            **base,
            "conclusion": "structure_work",
            "hint": f"需结构确认：{', '.join(structure)}。请先确认 Sheet 结构与列映射后再进入规整。",
        }
    if fields:
        return {
            **base,
            "conclusion": "field_work",
            "hint": f"需字段处理：{', '.join(fields)}。请先处理字段/物资/异常待办后再确认。",
        }
    return {
        **base,
        "conclusion": "staging_ready",
        "hint": "可进入规整：结构已识别，确认后写入业务库成为可用候选（不等于正式发布）。",
    }
