# -*- coding: utf-8 -*-
"""Step1 rule workbook/sheet profile (docs/03 §1.2) — no LLM."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.intake.profile import profile_from_evidence  # noqa: E402


def _cells(rows: list[tuple[str, int, str, str]]) -> pd.DataFrame:
    """Build cell evidence: (sheet, row, col, raw_value)."""
    recs = [
        {
            "file_id": "f1",
            "sheet": s,
            "row": r,
            "col": c,
            "raw_value": v,
            "value_type": "str",
        }
        for s, r, c, v in rows
    ]
    return pd.DataFrame(recs)


def test_empty_workbook():
    out = profile_from_evidence(
        pd.DataFrame(columns=["file_id", "sheet", "row", "col", "raw_value", "value_type"])
    )
    assert out["sheets"] == []
    assert out["workbook"]["sheet_count"] == 0
    assert out["source"] == "rule"


def test_history_and_reference_by_sheet_name():
    df = _cells(
        [
            ("历史备份-2023", 1, "A", "物资编码"),
            ("历史备份-2023", 1, "B", "数量"),
            ("历史备份-2023", 2, "A", "M1"),
            ("历史备份-2023", 2, "B", "10"),
            ("参考目录", 1, "A", "说明"),
            ("参考目录", 2, "A", "见附件"),
        ]
    )
    out = profile_from_evidence(df)
    by = {p["sheet"]: p for p in out["sheets"]}
    assert by["历史备份-2023"]["role_hint"] == "history_copy"
    assert by["参考目录"]["role_hint"] == "reference"


def test_summary_keyword_and_detail_inventory():
    df = _cells(
        [
            # detail inventory-like
            ("库存明细", 1, "A", "标题行"),
            ("库存明细", 2, "A", "物资编码"),
            ("库存明细", 2, "B", "物资名称"),
            ("库存明细", 2, "C", "库存数量"),
            ("库存明细", 2, "D", "单位"),
            ("库存明细", 3, "A", "A001"),
            ("库存明细", 3, "B", "电缆"),
            ("库存明细", 3, "C", "100"),
            ("库存明细", 3, "D", "米"),
            ("库存明细", 4, "A", "A002"),
            ("库存明细", 4, "B", "螺栓"),
            ("库存明细", 4, "C", "50"),
            ("库存明细", 4, "D", "个"),
            ("库存明细", 5, "A", "A003"),
            ("库存明细", 5, "B", "垫片"),
            ("库存明细", 5, "C", "20"),
            ("库存明细", 5, "D", "个"),
            # summary
            ("汇总表", 1, "A", "部门"),
            ("汇总表", 1, "B", "合计数量"),
            ("汇总表", 2, "A", "一车间"),
            ("汇总表", 2, "B", "1000"),
            ("汇总表", 3, "A", "合计"),
            ("汇总表", 3, "B", "1000"),
        ]
    )
    out = profile_from_evidence(df)
    by = {p["sheet"]: p for p in out["sheets"]}
    assert by["汇总表"]["role_hint"] == "summary"
    assert by["库存明细"]["role_hint"] == "detail"
    assert by["库存明细"]["header_row_candidates"][0] == 2
    assert by["库存明细"]["data_bounds"]["start_row"] >= 2
    assert by["库存明细"]["structure_hint"] == "standard_vertical"
    assert by["库存明细"]["needs_llm"] is False
    assert out["workbook"]["sheet_count"] == 2
    assert out["source"] == "rule"
    assert out["step"] == "workbook_profile"


def test_wide_export_and_unknown_needs_llm():
    # wide: 61 columns on header row
    wide = [("极宽导出", 1, chr(65 + i) if i < 26 else f"C{i}", f"col{i}") for i in range(61)]
    wide += [("极宽导出", 2, "A", "v")]
    # ambiguous: few mixed cells, no header aliases, no name signals
    amb = [
        ("杂表", 1, "A", "foo"),
        ("杂表", 1, "B", "1"),
        ("杂表", 2, "A", "bar"),
        ("杂表", 2, "B", "2"),
    ]
    out = profile_from_evidence(_cells(wide + amb))
    by = {p["sheet"]: p for p in out["sheets"]}
    assert by["极宽导出"]["role_hint"] == "wide_export"
    assert by["极宽导出"]["needs_llm"] is True
    assert by["杂表"]["role_hint"] == "unknown"
    assert by["杂表"]["needs_llm"] is True


def test_stacked_region_anomaly():
    rows = [
        ("堆叠", 1, "A", "物资编码"),
        ("堆叠", 1, "B", "数量"),
        ("堆叠", 2, "A", "A1"),
        ("堆叠", 2, "B", "1"),
        ("堆叠", 3, "A", "A2"),
        ("堆叠", 3, "B", "2"),
        # separator gap at row 10 — evidence has no cells in between
        ("堆叠", 10, "A", "物资编码"),
        ("堆叠", 10, "B", "数量"),
        ("堆叠", 11, "A", "B1"),
        ("堆叠", 11, "B", "3"),
    ]
    out = profile_from_evidence(_cells(rows))
    p = next(x for x in out["sheets"] if x["sheet"] == "堆叠")
    assert "stacked_regions" in p["anomalies"]
    assert p["needs_llm"] is True
