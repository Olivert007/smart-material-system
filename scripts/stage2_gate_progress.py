#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage2 gate 进度检查（每小时由 crond 调用，配合每 5min 的 check 心跳）。

输出一行可读摘要到 data/eval/stage2_gate_progress.log，
gate ready 时输出 STAGE2_GATE_READY、出现 fault 时输出 STAGE2_GATE_FAULT 醒目告警。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "eval" / "stage2_gate.json"
PROGRESS = ROOT / "data" / "eval" / "stage2_gate_progress.log"


def main() -> int:
    if not STATE.exists():
        line = f"[{datetime.now(timezone.utc).isoformat()}] STAGE2_GATE_NOT_STARTED"
        print(line, flush=True)
        return 0
    data = json.loads(STATE.read_text(encoding="utf-8"))
    state = data.get("state", "none")
    elapsed = data.get("elapsed_hours", 0.0)
    faults = data.get("faults", 0)
    ep_faults = data.get("endpoint_faults", {})
    checks = data.get("checks", [])
    up = checks[-1].get("up", {}) if checks else {}
    up_str = " ".join(f"{k}={v}" for k, v in sorted(up.items()))
    summary = (
        f"[{datetime.now(timezone.utc).isoformat()}] state={state} "
        f"elapsed_h={round(elapsed, 2)} faults={faults} endpoint_faults={ep_faults} {up_str}"
    )
    print(summary, flush=True)
    mark = ROOT / "data" / "eval" / "stage2_gate_progress.faults"
    prev = 0
    if mark.exists():
        try:
            prev = int(mark.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            prev = 0
    if state == "ready":
        print("STAGE2_GATE_READY", flush=True)
    elif faults > prev:
        print(f"STAGE2_GATE_FAULT (new={faults} prev={prev})", flush=True)
    mark.write_text(str(faults), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
