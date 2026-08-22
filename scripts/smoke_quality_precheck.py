#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: Step3 quality precheck (QUALITY_PRECHECK_OK)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.intake.quality_precheck import run_quality_precheck  # noqa: E402


def main() -> int:
    df = pd.DataFrame(
        {
            "物资编码": ["A1", "A1", "A2"],
            "物资名称": ["电缆", "电缆-dup", "螺栓"],
            "数量": ["10", "2024", "-1"],
        }
    )
    col_map = {
        "material_code": "物资编码",
        "material_name": "物资名称",
        "stock_qty": "数量",
    }
    q = run_quality_precheck(df, domain="inventory", col_map=col_map)
    assert q["source"] == "rule"
    assert q["blocking"] is True
    assert q["issue_counts"]["duplicate_pk"] >= 2
    assert q["issue_counts"]["qty_year_like"] >= 1
    assert q["issue_counts"]["qty_negative"] >= 1
    print("QUALITY_PRECHECK_OK")
    print(f"issues={q['issue_total']} counts={q['issue_counts']} dedup={q['suggested_dedup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
