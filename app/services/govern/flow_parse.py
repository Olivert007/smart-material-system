# -*- coding: utf-8 -*-
"""Flow text parsing primitives (docs/12 §4) — rule path only, no LLM."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

# Units commonly appearing after quantities in 305B / ZW texts
_UNIT = r"(?:个|台|包|根|对|条|部|套|把|米|卷|只|盒|件|张|块|支)"
_QTY_PATTERNS = [
    re.compile(rf"(?:入\s*库|出\s*库|领用|借用|使用)\s*(\d+(?:\.\d+)?)\s*({_UNIT})?", re.I),
    re.compile(rf"(\d+(?:\.\d+)?)\s*({_UNIT})(?![.\d])"),
]
_YEAR_ONLY = re.compile(r"^(?:19|20)\d{2}年?(?:之前|以前)?(?:采购|购入)?$")
_L3_TOKENS = {"已使用", "无", "无记录", "暂无", "/", "-", "--", "nan", "none"}
_DATE_HINT = re.compile(
    r"(?:19|20)\d{2}\s*[年./\-]\s*\d{1,2}"
    r"|(?:19|20)\d{2}\s*年"
    r"|(?:19|20)\d{2}-\d{2}-\d{2}"
)
_PERSON_SPLIT = re.compile(r"[、,，/／]")
# Chinese given-name-ish token after delimiters (heuristic)
_PERSON_TOKEN = re.compile(r"^[\u4e00-\u9fff]{2,4}$")


@dataclass
class FlowFields:
    flow_type: str  # IN / OUT
    flow_date: str | None = None  # ISO date or None
    quantity: float | None = None
    unit: str | None = None
    person: str | None = None
    purpose: str | None = None
    remark: str = ""
    parse_level: str = "L3"  # L1 / L2 / L3
    parse_source: str = "rule"
    source_segment: int = 0
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def text_norm(text: str) -> str:
    s = re.sub(r"\s+", "", (text or "").strip())
    return s.lower()


def split_flow_text(
    text: str,
    separators: list[str] | None = None,
) -> list[str]:
    """Split multi-entry cell into segments (docs/12 §4.1)."""
    raw = (text or "").strip()
    if not raw:
        return []
    seps = separators or ["；", ";", "。", "\n"]
    # Normalize newlines first
    s = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Split on separators while keeping intentional cuts before a new date/year
    pattern = "|".join(re.escape(x) for x in seps if x)
    parts = re.split(pattern, s) if pattern else [s]
    segments: list[str] = []
    for p in parts:
        p = p.strip(" ，,")
        if not p:
            continue
        # Further split when "；" already consumed but "。2026年" style missed —
        # also handle "…包。2026年…" already covered by 。
        # Heuristic: if segment contains another date mid-string after length, leave as-is
        # (primary split already handled). Soft-split on "；" already done.
        segments.append(p)

    # Soft re-split: "...入库4包 2026年6月..." without separator but next year starts
    refined: list[str] = []
    for seg in segments:
        cuts = [m.start() for m in re.finditer(
            r"(?:19|20)\d{2}\s*[年./\-]", seg
        )]
        if len(cuts) <= 1:
            refined.append(seg)
            continue
        # Only cut when prior chunk looks complete (has qty or person-ish) and cut not at 0
        last = 0
        for i, pos in enumerate(cuts):
            if pos == 0:
                continue
            prev = seg[last:pos].strip(" ，,;；")
            if prev and (_has_qty_token(prev) or "入库" in prev or "出库" in prev or "领用" in prev):
                refined.append(prev)
                last = pos
        tail = seg[last:].strip(" ，,;；")
        if tail:
            refined.append(tail)
    return [x for x in refined if x]


def _has_qty_token(text: str) -> bool:
    for pat in _QTY_PATTERNS:
        if pat.search(text):
            return True
    return False


def _parse_date(text: str) -> str | None:
    """Return ISO date string YYYY-MM-DD when possible; year-only → None (L2)."""
    s = (text or "").strip()
    if not s:
        return None
    # datetime-like "2022-08-17 00:00:00"
    m = re.search(r"((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"((?:19|20)\d{2})/(\d{1,2})/(\d{1,2})", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"((?:19|20)\d{2})\.(\d{1,2})\.(\d{1,2})", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"((?:19|20)\d{2})年(\d{1,2})月(\d{1,2})日?", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"((?:19|20)\d{2})年(\d{1,2})月", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), 1)
    # year-only / 之前采购 — date unknown
    if _YEAR_ONLY.match(re.sub(r"\s+", "", s)) or re.fullmatch(
        r"(?:19|20)\d{2}年?", re.sub(r"\s+", "", s)
    ):
        return None
    return None


def _iso(y: int, mo: int, d: int) -> str | None:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _extract_qty_unit(text: str) -> tuple[float | None, str | None]:
    """Extract quantity from text; never treat 4-digit year as quantity (FL5)."""
    # Strip date-like prefixes so year digits are not mistaken for qty
    scrubbed = text
    for pat in (
        r"(?:19|20)\d{2}-\d{1,2}-\d{1,2}(?:\s+\d{2}:\d{2}:\d{2})?",
        r"(?:19|20)\d{2}/\d{1,2}/\d{1,2}",
        r"(?:19|20)\d{2}\.\d{1,2}\.\d{1,2}",
        r"(?:19|20)\d{2}年\d{1,2}月\d{1,2}日?",
        r"(?:19|20)\d{2}年\d{1,2}月",
        r"(?:19|20)\d{2}年(?:之前|以前)?(?:采购|购入)?",
        r"(?:19|20)\d{2}年?",
    ):
        scrubbed = re.sub(pat, " ", scrubbed)

    for pat in _QTY_PATTERNS:
        m = pat.search(scrubbed)
        if not m:
            continue
        num = float(m.group(1))
        # Reject year-like 19xx/20xx with no unit and no 入/出库/领用 context nearby
        if 1900 <= num <= 2100 and not m.group(2):
            ctx = scrubbed[max(0, m.start() - 4) : m.end() + 4]
            if not re.search(r"入|出|领|借|用|库", ctx):
                continue
        unit = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        return num, unit
    return None, None


def _extract_person(text: str) -> str | None:
    # Patterns: "张停伟、陈乐言" / "李茜/" / "，张停伟维护"
    candidates: list[str] = []
    # After date comma: 2025年9月，张停伟…
    m = re.search(
        r"(?:年|日|\d)\s*[，,]\s*([\u4e00-\u9fff]{2,4}(?:[、,，][\u4e00-\u9fff]{2,4})*)",
        text,
    )
    if m:
        candidates.extend(_PERSON_SPLIT.split(m.group(1)))
    # Slash style: 2026.1.6/李茜/…
    m = re.search(r"\d\s*/\s*([\u4e00-\u9fff]{2,4})\s*/", text)
    if m:
        candidates.append(m.group(1))
    # 「…，徐吉领用」
    m = re.search(r"([\u4e00-\u9fff]{2,4})领用", text)
    if m:
        candidates.append(m.group(1))
    m = re.search(r"([\u4e00-\u9fff]{2,4})入库", text)
    if m:
        candidates.append(m.group(1))

    people = []
    for c in candidates:
        c = c.strip()
        if _PERSON_TOKEN.match(c) and c not in {"入库", "出库", "领用", "借用", "采购", "维护"}:
            if c not in people:
                people.append(c)
    return ";".join(people) if people else None


def _extract_purpose(text: str, *, flow_date: str | None, qty: float | None, person: str | None) -> str | None:
    s = text
    # remove dates
    for pat in (
        r"(?:19|20)\d{2}-\d{1,2}-\d{1,2}(?:\s+\d{2}:\d{2}:\d{2})?",
        r"(?:19|20)\d{2}/\d{1,2}/\d{1,2}",
        r"(?:19|20)\d{2}\.\d{1,2}\.\d{1,2}",
        r"(?:19|20)\d{2}年\d{1,2}月\d{1,2}日?",
        r"(?:19|20)\d{2}年\d{1,2}月",
        r"(?:19|20)\d{2}年(?:之前|以前)?(?:采购|购入)?",
    ):
        s = re.sub(pat, " ", s)
    if person:
        for p in person.split(";"):
            s = s.replace(p, " ")
    if qty is not None:
        s = re.sub(rf"(?:入\s*库|出\s*库|领用|借用)?\s*{re.escape(str(int(qty) if qty == int(qty) else qty))}\s*{_UNIT}?", " ", s)
    s = re.sub(r"[，,、/／；;]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ，,")
    return s or None


def extract_flow_fields(
    segment: str,
    *,
    flow_type: str,
    col_qty: float | None = None,
    col_unit: str | None = None,
    segment_count: int = 1,
    segment_index: int = 0,
    parse_source: str = "rule",
) -> FlowFields:
    """Extract one segment into typed fields + parse_level (docs/12 §4.2–4.5)."""
    raw = (segment or "").strip()
    flags: list[str] = []
    ft = flow_type.upper() if flow_type else "OUT"
    if ft not in ("IN", "OUT"):
        ft = "OUT"

    compact = re.sub(r"\s+", "", raw)
    if not compact or compact.lower() in _L3_TOKENS or compact in _L3_TOKENS:
        return FlowFields(
            flow_type=ft,
            remark=raw,
            parse_level="L3",
            parse_source=parse_source,
            source_segment=segment_index,
            flags=["empty_or_unusable"],
        )

    # Borrow tag (FL4)
    if re.search(r"借用|借出|内部流转", raw):
        flags.append("BORROW")
        ft = "OUT"

    flow_date = _parse_date(raw)
    qty_text, unit_text = _extract_qty_unit(raw)

    # §4.5 priority
    quantity: float | None = None
    unit: str | None = col_unit
    if qty_text is not None:
        quantity = qty_text
        if unit_text:
            unit = unit_text
        if col_qty is not None and abs(col_qty - qty_text) > 1e-6 and segment_count > 1:
            flags.append(f"qty_mismatch:col={col_qty}")
    elif segment_count == 1 and col_qty is not None:
        # P2 / P4: single segment borrows column qty
        quantity = float(col_qty)
        flags.append("qty_from_column")
    elif segment_count > 1 and col_qty is not None:
        # P3: multi-segment without per-segment qty → do NOT split evenly
        quantity = None
        flags.append("multi_seg_no_qty")
    else:
        quantity = None

    # Pure year cell → date None, may still take column qty (P4 via P2)
    if _YEAR_ONLY.match(compact) or re.fullmatch(r"(?:19|20)\d{2}年?", compact):
        flow_date = None
        flags.append("year_only")

    person = _extract_person(raw)
    purpose = _extract_purpose(raw, flow_date=flow_date, qty=quantity, person=person)

    remark = raw
    if "BORROW" in flags and "[BORROW]" not in remark:
        remark = f"{raw} [BORROW]"

    # Level
    if quantity is not None and flow_date is not None:
        level = "L1"
    elif quantity is None and flow_date is None and not person and not purpose:
        level = "L3"
    elif quantity is None and "multi_seg_no_qty" in flags:
        level = "L2"
    elif flow_date is None and quantity is None and compact in {"已使用", "无"}:
        level = "L3"
    else:
        # partial: has date or qty or person
        if quantity is None and flow_date is None and not _DATE_HINT.search(raw):
            level = "L3" if not person and not purpose else "L2"
        else:
            level = "L2"

    # L1 hard requirement: date + quantity (12 §4.4)
    if level == "L1" and (quantity is None or flow_date is None):
        level = "L2"

    return FlowFields(
        flow_type=ft,
        flow_date=flow_date,
        quantity=quantity,
        unit=unit,
        person=person,
        purpose=purpose,
        remark=remark,
        parse_level=level,
        parse_source=parse_source,
        source_segment=segment_index,
        flags=flags,
    )


def parse_flow_cell(
    text: str,
    *,
    flow_type: str,
    col_qty: float | None = None,
    col_unit: str | None = None,
    separators: list[str] | None = None,
    parse_source: str = "rule",
) -> list[FlowFields]:
    """Full cell → 0..N FlowFields (docs/12 §3A)."""
    segments = split_flow_text(text, separators)
    if not segments:
        return []
    n = len(segments)
    return [
        extract_flow_fields(
            seg,
            flow_type=flow_type,
            col_qty=col_qty,
            col_unit=col_unit,
            segment_count=n,
            segment_index=i,
            parse_source=parse_source,
        )
        for i, seg in enumerate(segments)
    ]


def example_key(text: str) -> str:
    return hashlib.sha256(text_norm(text).encode()).hexdigest()[:24]
