#!/usr/bin/env python3
"""Print / persist FLOW_* quality baseline (docs/12 A9)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))

from app.repositories import init_meta  # noqa: E402
from app.services.metrics import ensure_flow_metrics_draft, flow_quality_baseline  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()
    init_meta()
    ensure_flow_metrics_draft()
    base = flow_quality_baseline()
    print(json.dumps(base, ensure_ascii=False, indent=2, default=str))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(base, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("wrote", out)
    print("BASELINE_OK" if base.get("flow_metrics_all_draft") else "BASELINE_CHECK")


if __name__ == "__main__":
    main()
