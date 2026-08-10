# -*- coding: utf-8 -*-
"""从 ledger_source_samples.json 生成 4-sheet 台账 xlsx（E2E / 脚本复用）。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "ledger_source_samples.json"


def build_ledger_xlsx_from_fixture(
    *,
    fixture_path: Path | None = None,
    out_path: Path | None = None,
) -> Path:
    from openpyxl import Workbook

    fixture_path = fixture_path or FIXTURE
    fx = json.loads(fixture_path.read_text(encoding="utf-8"))
    wb = Workbook()
    wb.remove(wb.active)
    for sh in fx["sheets"]:
        ws = wb.create_sheet(title=sh["sheet"])
        headers = sh["headers"]
        ws.append(headers)
        for row in sh["sample_rows"]:
            ws.append([row.get(h, "") for h in headers])
    name = fx.get("source_file") or "ledger_sample.xlsx"
    if out_path is None:
        out_path = Path(tempfile.mkdtemp(prefix="ledger_xlsx_")) / name
    else:
        out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def expected_row_counts() -> dict[str, int]:
    """fixture 样例行数（扣除序号「例」示例行后）。"""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for sh in fx["sheets"]:
        n = 0
        for row in sh["sample_rows"]:
            seq = str(row.get("序号", "")).strip()
            if seq in {"例", "示例", "example"}:
                continue
            n += 1
        out[sh["sheet"]] = n
    return out
