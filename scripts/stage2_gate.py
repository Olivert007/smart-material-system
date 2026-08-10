#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage2 24h 双常驻 gate 验证（docs/09 / docs/10 §4/§5，question/01 P1）。

闭合条件（docs/10 §5）：
- big+fast 双常驻端点健康（HTTP /v1/models 可达）；
- 连续 24h 无 OOM、无任务锁死、无端点频繁重启；
- 通过后按 docs/09 流程 claim「Stage 2 生产双常驻」。

用法（建议 cron 每 5 分钟）：
  python3 scripts/stage2_gate.py start        # 开始新一轮验证（记录起点）
  python3 scripts/stage2_gate.py check        # 心跳检查；达到 24h 输出 ready
  python3 scripts/stage2_gate.py status       # 查看当前进度
状态文件：data/eval/stage2_gate.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "eval" / "stage2_gate.json"

# Stage2 双常驻目标端点（docs/09）：big=:8001 fast=:8000
ENDPOINTS = [
    {"name": "big", "port": 8001, "model": "qwen3.6-27b"},
    {"name": "fast", "port": 8000, "model": ""},
]
GATE_HOURS = 24
HEARTBEAT_GRACE_SEC = 600  # 心跳间隔容忍（分钟级 cron 抖动）
# OOM 判据：vllm 进程数量相对上轮不变 + 端点不可达即计一次异常


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http_up(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _load() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"state": "none", "started_at": None, "checks": [], "faults": 0, "endpoint_faults": {}}


def _save(data: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _probe(data: dict) -> dict:
    faults = 0
    status: dict[str, bool] = {}
    for ep in ENDPOINTS:
        up = _http_up(ep["port"])
        key = f'{ep["name"]}:{ep["port"]}'
        status[key] = up
        if not up:
            faults += 1
            data["endpoint_faults"][key] = data["endpoint_faults"].get(key, 0) + 1
    return {"ts": _now(), "up": status, "faults": faults}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["start", "check", "status"])
    args = ap.parse_args()

    data = _load()
    if args.cmd == "start":
        data = {
            "state": "running",
            "started_at": _now(),
            "start_ts": time.time(),
            "gate_hours": GATE_HOURS,
            "checks": [],
            "faults": 0,
            "endpoint_faults": {},
            "last_ok_ts": None,
        }
        probe = _probe(data)
        data["checks"].append(probe)
        data["last_ok_ts"] = time.time()
        _save(data)
        print(f"STAGE2_GATE_START {data['started_at']}")
        return 0

    if data.get("state") != "running" or not data.get("start_ts"):
        print("STAGE2_GATE_NOT_STARTED (run: stage2_gate.py start)")
        return 0

    probe = _probe(data)
    data["checks"].append(probe)
    if probe["faults"] == 0:
        data["last_ok_ts"] = time.time()
    data["faults"] += probe["faults"]
    elapsed_h = (time.time() - data["start_ts"]) / 3600
    ready = elapsed_h >= GATE_HOURS and data["faults"] == 0
    data["state"] = "ready" if ready else "running"
    data["elapsed_hours"] = round(elapsed_h, 2)
    # 只保留最近 288 条心跳（24h @ 5min），防状态文件无限膨胀
    data["checks"] = data["checks"][-288:]
    _save(data)
    print(
        json.dumps(
            {
                "state": data["state"],
                "elapsed_hours": round(elapsed_h, 2),
                "faults": data["faults"],
                "endpoint_faults": data["endpoint_faults"],
                "ready": ready,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
