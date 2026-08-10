#!/usr/bin/env python3
"""Activate FLOW_* metrics when 08/12 gate is ready (docs/12 D4)."""
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
from app.services.metrics import activate_flow_metrics, flow_activation_gate  # noqa: E402
from app.services.metric_fixtures import run_metric_fixtures  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--actor", default="ops:cli")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--metric-id", action="append", default=[])
    args = ap.parse_args()
    init_meta()
    fx = run_metric_fixtures()
    print(json.dumps({"fixtures": fx}, ensure_ascii=False, indent=2))
    gate = flow_activation_gate()
    print(json.dumps({"gate": {k: gate[k] for k in ("ready", "checks", "missing")}}, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("DRY_RUN")
        return
    if not gate["ready"]:
        print("GATE_BLOCKED", gate["missing"])
        raise SystemExit(2)
    out = activate_flow_metrics(
        actor=args.actor,
        metric_ids=args.metric_id or None,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print("FLOW_ACTIVATE_OK")


if __name__ == "__main__":
    main()
