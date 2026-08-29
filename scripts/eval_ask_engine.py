#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare legacy vs Vanna ask engines on 20 material questions (docs/19 Step5).

用法：
  PYTHONPATH=. python3 scripts/eval_ask_engine.py
  PYTHONPATH=. python3 scripts/eval_ask_engine.py --offline

结果写入：data/eval/results/ask_engine_compare.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))
os.environ.setdefault("OPS_TOKEN", os.environ.get("OPS_TOKEN", "dev-ops-token-change-me"))

from app.services.query.ask_engine_eval import run_compare  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare legacy vs Vanna ask engines")
    ap.add_argument("--offline", action="store_true", help="结构自检，不调用本地模型")
    ap.add_argument("--out", type=Path, default=None, help="输出 JSON 路径")
    args = ap.parse_args()
    out = run_compare(offline=args.offline, out_path=args.out)
    print(
        json.dumps(
            {k: out[k] for k in ("ok", "offline", "n_cases", "summary", "winner", "path")},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
