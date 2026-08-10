#!/usr/bin/env python3
"""从 ledger_source_samples.json 生成 4-sheet 台账 xlsx。

用法:
  python3 scripts/build_ledger_fixture_xlsx.py [输出路径]
默认写入 data/samples/ce84beaa91ca.xlsx
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from ledger_xlsx_util import build_ledger_xlsx_from_fixture  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "samples" / "ce84beaa91ca.xlsx"
    path = build_ledger_xlsx_from_fixture(out_path=out)
    print(f"written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
