#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eval set size smoke: text2sql >= 50 (EVAL_SQL50_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_eval50_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)

sys.path.insert(0, str(ROOT))

from app.services.eval_skel import SQL_SAMPLES, ensure_eval_skeleton  # noqa: E402


def main() -> int:
    assert len(SQL_SAMPLES) >= 50, len(SQL_SAMPLES)
    root = ensure_eval_skeleton(force=True)
    lines = [ln for ln in (root / "text2sql.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 50, len(lines)
    # structural sanity
    import json

    for ln in lines[:3]:
        row = json.loads(ln)
        assert "question" in row and "must_contain" in row
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "50" in readme or str(len(SQL_SAMPLES)) in readme
    print("EVAL_SQL50_OK")
    print(f"sql_samples={len(SQL_SAMPLES)} jsonl={len(lines)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
