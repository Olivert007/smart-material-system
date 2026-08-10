# -*- coding: utf-8 -*-
"""Step1 workbook/sheet profile — rule-only (docs/03 §1.2).

No LLM. Consumes cell-evidence DataFrame (file_id, sheet, row, col, raw_value).
LLM sheet profile for unknown/ambiguous sheets is a later Stage task.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pandas as pd

from app.repositories import meta_tx

# --- thresholds (docs/03 §1.2) ---
WIDE_COL_THRESHOLD = 60
EMPTY_DENSITY_THRESHOLD = 0.02
HEADER_PROBE_ROWS = 12
MIN_DETAIL_DATA_ROWS = 3
MIN_HEADER_TEXT_CELLS = 3
TEXT_RATIO_FOR_HEADER = 0.55

_SUMMARY_KW = re.compile(r"(合计|总计|汇总|小计)")
_HISTORY_NAME = re.compile(r"(历史|旧版|旧表|备份|副本|bak|backup|copy)", re.I)
_HISTORY_DATE_SUFFIX = re.compile(r"(20\d{2}[-./年]?\d{0,2}|_\d{6,8})$")
_REF_NAME = re.compile(r"(参考|目录|清单说明|说明|readme)", re.I)
_NUMERIC_RE = re.compile(r"^[\d,.\-\+eE%]+$")

_HEADER_HINTS = (
    "编码",
    "编号",
    "名称",
    "规格",
    "数量",
    "单位",
    "库存",
    "物资",
    "资产",
    "区域",
    "部门",
    "日期",
    "入库",
    "出库",
    "备注",
)


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def _is_textish(v: str) -> bool:
    s = (v or "").strip()
    if not s or s.lower() in {"nan", "none"}:
        return False
    if _NUMERIC_RE.match(s.replace(",", "")):
        return False
    return True


def _row_text_score(values: list[str]) -> tuple[float, int]:
    nonempty = [
        str(v).strip()
        for v in values
        if str(v).strip() and str(v).strip().lower() not in {"nan", "none"}
    ]
    if not nonempty:
        return 0.0, 0
    text_n = sum(1 for v in nonempty if _is_textish(v))
    return text_n / len(nonempty), text_n


def _header_hint_hits(values: list[str]) -> int:
    hits = 0
    for v in values:
        s = str(v).strip()
        if any(h in s for h in _HEADER_HINTS):
            hits += 1
    return hits


def _sheet_frame(df: pd.DataFrame, sheet: str) -> pd.DataFrame:
    sub = df.loc[df["sheet"].astype(str) == sheet].copy()
    if sub.empty:
        return sub
    sub["row"] = pd.to_numeric(sub["row"], errors="coerce")
    sub = sub.dropna(subset=["row"])
    sub["row"] = sub["row"].astype(int)
    sub = sub.loc[sub["row"] > 0]
    return sub


def _profile_one_sheet(sheet: str, sub: pd.DataFrame) -> dict[str, Any]:
    if sub.empty:
        return {
            "sheet": sheet,
            "rows": 0,
            "cols": 0,
            "density": 0.0,
            "role_hint": "empty",
            "role_confidence": 1.0,
            "header_row_candidates": [],
            "data_bounds": {"start_row": None, "end_row": None},
            "structure_hint": "empty",
            "adapter_hint": "none",
            "anomalies": ["empty_sheet"],
            "needs_llm": False,
            "signals": ["empty"],
        }

    max_row = int(sub["row"].max())
    cols = sorted({str(c) for c in sub["col"].tolist()})
    n_cols = len(cols)
    n_cells = int(len(sub))
    grid = max(max_row * max(n_cols, 1), 1)
    density = n_cells / grid

    by_row: dict[int, list[str]] = {}
    for r, v in zip(sub["row"].tolist(), sub["raw_value"].tolist()):
        by_row.setdefault(int(r), []).append(str(v) if v is not None else "")

    candidates: list[tuple[float, int, int]] = []
    probe_limit = min(HEADER_PROBE_ROWS, max_row)
    for r in range(1, probe_limit + 1):
        vals = by_row.get(r, [])
        ratio, text_n = _row_text_score(vals)
        hint = _header_hint_hits(vals)
        # Allow short header rows when domain tokens hit (e.g. 编码+数量).
        if hint < 2 and text_n < MIN_HEADER_TEXT_CELLS and len(vals) < MIN_HEADER_TEXT_CELLS:
            continue
        if ratio < TEXT_RATIO_FOR_HEADER and hint < 2:
            continue
        score = ratio + 0.15 * hint + 0.05 * min(len(vals), 20)
        candidates.append((score, r, hint))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    header_rows = [r for _, r, _ in candidates[:3]]

    header_row = header_rows[0] if header_rows else None
    data_start = (header_row + 1) if header_row else (1 if by_row else None)
    data_end = max_row if max_row > 0 else None
    data_row_count = 0
    if data_start and data_end and data_end >= data_start:
        data_row_count = sum(1 for r in by_row if r >= data_start)

    anomalies: list[str] = []
    signals: list[str] = []

    # stacked regions: empty row gap (>=3 missing rows) between two header-like bands
    hdr_set = {r for _score, r, _h in candidates}
    sorted_rows = sorted(by_row.keys())
    for i in range(len(sorted_rows) - 1):
        a, b = sorted_rows[i], sorted_rows[i + 1]
        if b - a < 4:
            continue
        # find nearest header-like row at/before a and at/after b
        left = max((r for r in hdr_set if r <= a), default=None)
        right = min((r for r in hdr_set if r >= b), default=None)
        if left is not None and right is not None and right - left >= 4:
            anomalies.append("stacked_regions")
            signals.append(f"stack_gap:{left}-{right}")
            break

    if len(header_rows) >= 2 and header_rows[1] == header_rows[0] + 1:
        # Only adjacent *header-token* rows — not text-heavy data rows.
        top_hints = {r: h for _s, r, h in candidates}
        if top_hints.get(header_rows[0], 0) >= 2 and top_hints.get(header_rows[1], 0) >= 2:
            anomalies.append("multi_level_header")
            signals.append("adjacent_header_rows")

    all_text = " ".join(str(v) for v in sub["raw_value"].tolist())
    has_summary_kw = bool(_SUMMARY_KW.search(all_text))

    role = "unknown"
    confidence = 0.4
    needs_llm = False

    # Name-based roles first (sheet title is strong signal even on sparse sheets).
    if _HISTORY_NAME.search(sheet):
        role, confidence = "history_copy", 0.95
        signals.append("name:history")
    elif _HISTORY_DATE_SUFFIX.search(sheet.strip()):
        role, confidence = "history_copy", 0.8
        signals.append("name:date_suffix")
    elif _REF_NAME.search(sheet):
        role, confidence = "reference", 0.9
        signals.append("name:reference")

    if role == "unknown":
        if n_cells <= 2 and max_row <= 2:
            role, confidence = "empty", 0.9
            signals.append("low_fill")
        elif density < EMPTY_DENSITY_THRESHOLD:
            role, confidence = "empty", 0.85
            signals.append("low_density")

    if role == "unknown" and n_cols > WIDE_COL_THRESHOLD:
        role, confidence = "wide_export", 0.95
        anomalies.append("wide_columns")
        signals.append(f"cols:{n_cols}")
        needs_llm = True

    if role == "unknown" and has_summary_kw:
        role, confidence = "summary", 0.85
        signals.append("kw:summary")

    if role == "unknown" and header_row and data_row_count >= MIN_DETAIL_DATA_ROWS:
        hint_hits = candidates[0][2] if candidates else 0
        if hint_hits >= 2 or (candidates and candidates[0][0] >= 0.85):
            role, confidence = "detail", 0.8 if hint_hits >= 2 else 0.65
            signals.append("header+data")
        elif n_cols >= 3 and data_row_count >= MIN_DETAIL_DATA_ROWS:
            role, confidence = "detail", 0.55
            signals.append("wideish_table")

    if role == "unknown":
        needs_llm = True
        signals.append("unresolved")

    if "stacked_regions" in anomalies or "multi_level_header" in anomalies:
        needs_llm = True
    if role == "wide_export":
        needs_llm = True

    structure = "unknown"
    adapter = "none"
    if role == "empty":
        structure = "empty"
    elif "stacked_regions" in anomalies:
        structure = "stacked_regions"
        adapter = "split_regions"
    elif "multi_level_header" in anomalies and role in {"detail", "unknown", "summary"}:
        structure = "multi_level_header"
        adapter = "rebuild_header"
    elif role in {"detail", "summary", "history_copy"} and header_row and n_cols >= 3:
        structure = "standard_vertical"
        adapter = "none"
    elif role == "wide_export":
        structure = "wide_export"
        adapter = "column_sample"
    elif role == "reference":
        structure = "report_only"
        adapter = "none"
    elif role == "detail" and header_row:
        structure = "standard_vertical"
        adapter = "none"

    return {
        "sheet": sheet,
        "rows": max_row,
        "cols": n_cols,
        "density": round(density, 4),
        "role_hint": role,
        "role_confidence": round(confidence, 3),
        "header_row_candidates": header_rows,
        "data_bounds": {
            "start_row": data_start,
            "end_row": data_end,
            "data_row_count": data_row_count,
        },
        "structure_hint": structure,
        "adapter_hint": adapter,
        "anomalies": anomalies,
        "needs_llm": bool(needs_llm),
        "signals": signals,
    }


def profile_from_evidence(df: pd.DataFrame | None) -> dict[str, Any]:
    """Pure rule workbook profile from cell-evidence frame."""
    if df is None or df.empty or "sheet" not in getattr(df, "columns", []):
        return {
            "step": "workbook_profile",
            "source": "rule",
            "workbook": {"sheet_count": 0, "needs_llm_sheets": [], "role_counts": {}},
            "sheets": [],
        }

    sheets = []
    for sheet in sorted({str(s) for s in df["sheet"].tolist()}):
        sheets.append(_profile_one_sheet(sheet, _sheet_frame(df, sheet)))

    role_counts: dict[str, int] = {}
    needs_llm_sheets: list[str] = []
    for p in sheets:
        role_counts[p["role_hint"]] = role_counts.get(p["role_hint"], 0) + 1
        if p.get("needs_llm"):
            needs_llm_sheets.append(p["sheet"])

    return {
        "step": "workbook_profile",
        "source": "rule",
        "workbook": {
            "sheet_count": len(sheets),
            "needs_llm_sheets": needs_llm_sheets,
            "role_counts": role_counts,
        },
        "sheets": sheets,
    }


def save_workbook_profile(file_id: str, payload: dict[str, Any]) -> str:
    """Persist workbook_profile into intake_report; replace prior profile for file."""
    report_id = _sid()
    blob = json.dumps(payload, ensure_ascii=False)
    with meta_tx() as con:
        con.execute(
            "DELETE FROM intake_report WHERE file_id=? AND report_type='workbook_profile'",
            [file_id],
        )
        con.execute(
            """
            INSERT INTO intake_report (report_id, file_id, report_type, payload_json)
            VALUES (?, ?, 'workbook_profile', ?)
            """,
            [report_id, file_id, blob],
        )
    return report_id


def get_workbook_profile(file_id: str) -> dict[str, Any] | None:
    with meta_tx() as con:
        row = con.execute(
            """
            SELECT report_id, file_id, report_type, payload_json, created_at
            FROM intake_report
            WHERE file_id=? AND report_type='workbook_profile'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [file_id],
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"] or "{}")
    return {
        "report_id": row["report_id"],
        "file_id": row["file_id"],
        "report_type": row["report_type"],
        "created_at": row["created_at"],
        "profile": payload,
    }


def profile_file_evidence(file_id: str) -> dict[str, Any]:
    """Load evidence parquet and build+persist workbook profile."""
    from app.services.evidence import evidence_path

    path = evidence_path(file_id)
    if not path.exists():
        raise FileNotFoundError(f"evidence missing: {file_id}")
    df = pd.read_parquet(path)
    payload = profile_from_evidence(df)
    report_id = save_workbook_profile(file_id, payload)
    return {**payload, "report_id": report_id, "file_id": file_id}
