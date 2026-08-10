# -*- coding: utf-8 -*-
"""Flow parse / LLM suggest eval cases (docs/12 B4)."""
from __future__ import annotations

import json
from pathlib import Path

from app import config

# Small gold set from 12 §1.1 / fixtures — single-cell focus for LLM suggest.
FLOW_LLM_SAMPLES: list[dict] = [
    {
        "id": "out_slash_style",
        "text": "2026.1.6/李茜/西坝大楼2408会议室搭建备用使用",
        "flow_type": "OUT",
        "col_qty": 1,
        "expect": {
            "flow_type": "OUT",
            "quantity": 1.0,
            "flow_date": "2026-01-06",
            "person_contains": "李茜",
            "parse_level_in": ["L1", "L2"],
            "forbid_quantity": [2026],
        },
    },
    {
        "id": "out_with_qty_in_text",
        "text": "2025年10月，徐吉领用3个，用于机房音频配线",
        "flow_type": "OUT",
        "expect": {
            "flow_type": "OUT",
            "quantity": 3.0,
            "unit": "个",
            "person_contains": "徐吉",
            "parse_level_in": ["L1", "L2"],
            "forbid_quantity": [2025],
        },
    },
    {
        "id": "year_only_not_qty",
        "text": "2023年",
        "flow_type": "IN",
        "col_qty": 10,
        "expect": {
            "flow_type": "IN",
            "quantity": 10.0,
            "flow_date": None,
            "parse_level_in": ["L2", "L3"],
            "forbid_quantity": [2023, 2025, 2026],
        },
    },
    {
        "id": "year_before_purchase",
        "text": "2024年之前采购",
        "flow_type": "IN",
        "col_qty": 5,
        "expect": {
            "flow_type": "IN",
            "quantity": 5.0,
            "flow_date": None,
            "parse_level_in": ["L2", "L3"],
            "forbid_quantity": [2024],
        },
    },
    {
        "id": "pure_datetime_cell",
        "text": "2022-08-17 00:00:00",
        "flow_type": "IN",
        "col_qty": 2,
        "col_unit": "台",
        "expect": {
            "flow_type": "IN",
            "quantity": 2.0,
            "unit": "台",
            "flow_date": "2022-08-17",
            "parse_level_in": ["L1", "L2"],
            "forbid_quantity": [2022],
        },
    },
    {
        "id": "l3_used",
        "text": "已使用",
        "flow_type": "OUT",
        "expect": {
            "flow_type": "OUT",
            "quantity": None,
            "parse_level_in": ["L3"],
            "forbid_quantity": [2023, 2024, 2025, 2026],
        },
    },
    {
        "id": "borrow_as_out",
        "text": "2024.12.30 借用给宜昌分部",
        "flow_type": "OUT",
        "col_qty": 1,
        "expect": {
            "flow_type": "OUT",
            "quantity": 1.0,
            "flag_contains": "BORROW",
            "parse_level_in": ["L1", "L2"],
            "forbid_quantity": [2024],
        },
    },
    {
        "id": "dot_date_out_qty",
        "text": "2026.4.14出库至溪洛渡1个",
        "flow_type": "OUT",
        "expect": {
            "flow_type": "OUT",
            "quantity": 1.0,
            "unit": "个",
            "flow_date": "2026-04-14",
            "parse_level_in": ["L1", "L2"],
            "forbid_quantity": [2026],
        },
    },
    {
        "id": "multi_person_label",
        "text": "2025.07，张停伟、陈乐言，标签打印",
        "flow_type": "OUT",
        "col_qty": 2,
        "expect": {
            "flow_type": "OUT",
            "quantity": 2.0,
            "person_contains": "张停伟",
            "parse_level_in": ["L1", "L2"],
            "forbid_quantity": [2025],
        },
    },
    {
        "id": "in_with_qty_pack",
        "text": "2025年6月，张停伟维护材料采购，沈鸿入库4包",
        "flow_type": "IN",
        "expect": {
            "flow_type": "IN",
            "quantity": 4.0,
            "unit": "包",
            "parse_level_in": ["L1", "L2"],
            "forbid_quantity": [2025],
        },
    },
    {
        "id": "out_to_xiluodu",
        "text": "2026.4.14出库至溪洛渡1个",
        "flow_type": "OUT",
        "expect": {
            "flow_type": "OUT",
            "quantity": 1.0,
            "parse_level_in": ["L1", "L2"],
            "forbid_quantity": [2026],
        },
        "note": "duplicate style check for stability",
    },
    {
        "id": "emptyish_slash",
        "text": "/",
        "flow_type": "OUT",
        "expect": {
            "flow_type": "OUT",
            "quantity": None,
            "parse_level_in": ["L3"],
            "forbid_quantity": [2023, 2024, 2025, 2026],
        },
    },
]


def ensure_flow_eval(*, force: bool = False) -> Path:
    root = config.EVAL
    root.mkdir(parents=True, exist_ok=True)
    path = root / "flow_parse_llm.jsonl"
    if force or not path.exists():
        with path.open("w", encoding="utf-8") as f:
            for row in FLOW_LLM_SAMPLES:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    readme = root / "README.md"
    prev = readme.read_text(encoding="utf-8") if readme.exists() else ""
    block = (
        f"- `flow_parse_llm.jsonl` — {len(FLOW_LLM_SAMPLES)} flow suggest gold cases "
        "(rule + optional LLM; docs/12 B4)\n"
        "- `results/flow_eval_*.json` — `scripts/run_eval_flow.py` outputs\n"
    )
    if "flow_parse_llm.jsonl" not in prev:
        if not prev:
            prev = "# Eval skeleton (Stage 1)\n\n"
        readme.write_text(prev.rstrip() + "\n" + block, encoding="utf-8")
    return root
