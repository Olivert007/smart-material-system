#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Initialize Vanna ask context from schema / metrics / fewshot (docs/19 Step3).

用法：
  PYTHONPATH=. python3 scripts/train_vanna_ask.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.query.vanna_train import train_vanna_ask  # noqa: E402


def main() -> int:
    out = train_vanna_ask(replace=True)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not out.get("ok"):
        return 1
    if (out.get("question_sql_count") or 0) < 5:
        print("WARN: question_sql_count low; check metrics/fewshot seeds", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
