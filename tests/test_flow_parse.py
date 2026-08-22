# -*- coding: utf-8 -*-
"""Unit tests for docs/12 flow_parse primitives (A2)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.govern.flow_parse import parse_flow_cell, split_flow_text  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "flow_texts.json"


def _check_one(case: dict) -> None:
    text = case["text"]
    segs = split_flow_text(text)
    assert len(segs) == case["expect_segments"], (
        f"{case['id']}: segments={segs!r} expect {case['expect_segments']}"
    )
    rows = parse_flow_cell(
        text,
        flow_type=case["flow_type"],
        col_qty=case.get("col_qty"),
        col_unit=case.get("col_unit"),
    )
    assert len(rows) == len(case["expect"]), f"{case['id']}: row count"
    for i, (got, exp) in enumerate(zip(rows, case["expect"])):
        prefix = f"{case['id']}[{i}]"
        if "parse_level" in exp:
            assert got.parse_level == exp["parse_level"], (
                f"{prefix}: level {got.parse_level} != {exp['parse_level']} flags={got.flags} qty={got.quantity}"
            )
        if "quantity" in exp:
            if exp["quantity"] is None:
                assert got.quantity is None, f"{prefix}: qty should be None got {got.quantity}"
            else:
                assert got.quantity is not None and abs(got.quantity - exp["quantity"]) < 1e-6, (
                    f"{prefix}: qty {got.quantity} != {exp['quantity']}"
                )
        if "unit" in exp and exp["unit"]:
            assert got.unit == exp["unit"], f"{prefix}: unit {got.unit}"
        if "flow_date" in exp:
            assert got.flow_date == exp["flow_date"], f"{prefix}: date {got.flow_date}"
        if "flow_type" in exp:
            assert got.flow_type == exp["flow_type"], f"{prefix}: type"
        if "person_contains" in exp:
            assert got.person and exp["person_contains"] in got.person, (
                f"{prefix}: person {got.person}"
            )
        if "min_person_parts" in exp:
            parts = (got.person or "").split(";") if got.person else []
            assert len([p for p in parts if p]) >= exp["min_person_parts"], (
                f"{prefix}: person parts {got.person}"
            )
        if "flag_contains" in exp:
            assert exp["flag_contains"] in got.flags, f"{prefix}: flags {got.flags}"
        if "forbid_quantity" in exp:
            for bad in exp["forbid_quantity"]:
                assert got.quantity != float(bad), f"{prefix}: year-as-qty {bad}"


def main() -> None:
    cases = json.loads(FIX.read_text(encoding="utf-8"))
    for case in cases:
        _check_one(case)
        print("OK", case["id"])
    print("FLOW_PARSE_OK", len(cases))


if __name__ == "__main__":
    main()
