#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: Step1 rule workbook profile after evidence (PROFILE_STEP1_OK)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories import init_meta, meta_tx  # noqa: E402
from app.services.intake.profile import get_workbook_profile, profile_from_evidence, save_workbook_profile  # noqa: E402


def main() -> int:
    init_meta()
    rows = []
    for r, vals in enumerate(
        [
            ["物资编码", "物资名称", "库存数量", "单位"],
            ["A1", "电缆", "10", "米"],
            ["A2", "螺栓", "20", "个"],
            ["A3", "垫片", "5", "个"],
        ],
        start=2,
    ):
        for i, v in enumerate(vals):
            rows.append(
                {
                    "file_id": "smoke_profile",
                    "sheet": "库存明细",
                    "row": r,
                    "col": chr(65 + i),
                    "raw_value": v,
                    "value_type": "str",
                }
            )
    rows.append(
        {
            "file_id": "smoke_profile",
            "sheet": "历史备份",
            "row": 1,
            "col": "A",
            "raw_value": "旧数据",
            "value_type": "str",
        }
    )
    df = pd.DataFrame(rows)
    payload = profile_from_evidence(df)
    assert payload["source"] == "rule"
    by = {p["sheet"]: p for p in payload["sheets"]}
    assert by["库存明细"]["role_hint"] == "detail", by["库存明细"]
    assert by["历史备份"]["role_hint"] == "history_copy", by["历史备份"]

    fid = "smoke_profile_file"
    with meta_tx() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO file_batch
            (file_id, filename, format, sha256, stored_path, status)
            VALUES (?, 'smoke.xlsx', 'xlsx', 'x', '/tmp/smoke.xlsx', 'evidence_done')
            """,
            [fid],
        )
    rid = save_workbook_profile(fid, payload)
    got = get_workbook_profile(fid)
    assert got and got["report_id"] == rid
    assert got["profile"]["workbook"]["sheet_count"] == 2

    print("PROFILE_STEP1_OK")
    print(
        f"sheets={payload['workbook']['sheet_count']} "
        f"roles={payload['workbook']['role_counts']} "
        f"needs_llm={payload['workbook']['needs_llm_sheets']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
