#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vLLM 模型端点内存看门狗（P0-3）。

- 健康检查：big=:8001 / fast=:8000 / embed=:8002 的 /v1/models 是否可达；
- 内存监控：vllm 进程主机 RSS 与系统 MemAvailable 余量，超阈值告警；
- 自愈（--heal）：挂掉的端点自动拉起（big 优先；fast/embed 由 models.sh 内存余量门防 OOM）；
- 内存看门（--guard）：MemAvailable < 阈值时调 models.sh mem-guard（停 embed→fast，不停 big）。

用法:
  python3 scripts/models_watchdog.py                 # 单次检查，输出一行 JSON
  python3 scripts/models_watchdog.py --heal          # 单次检查 + 自动拉起
  python3 scripts/models_watchdog.py --guard         # 单次检查 + 内存看门动作
  python3 scripts/models_watchdog.py --daemon --interval 300 --heal --guard   # 常驻循环

建议 cron 每 5 分钟：*/5 * * * * cd /workspace/2026-07/smart-material-system && \
  python3 scripts/models_watchdog.py --heal --guard >> /tmp/models_watchdog.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENDPOINTS = [
    {"name": "big", "port": 8001, "heal": True},
    {"name": "fast", "port": 8000, "heal": False},
    {"name": "embed", "port": 8002, "heal": False},
]
# vllm 进程主机 RSS 告警阈值（GB）；GB10 统一内存 128GB
RSS_ALARM_GB = float(os.environ.get("WATCHDOG_RSS_ALARM_GB", "100"))
# 系统 MemAvailable 余量告警阈值（GB）
MEM_LOW_ALARM_GB = float(os.environ.get("WATCHDOG_MEM_LOW_GB", "20"))
# --guard 触发阈值（GB）：低于则调 models.sh mem-guard（对齐 GUARD_EMBED_GB=15）
WATCHDOG_GUARD_GB = float(os.environ.get("WATCHDOG_GUARD_GB", "15"))


def mem_available_gb() -> float:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return float(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return float("nan")


def find_vllm_pids(port: int) -> list[int]:
    """扫描 /proc 中 cmdline 含 '--port <port>' 的 vllm 进程。"""
    pids: list[int] = []
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            try:
                cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
            except OSError:
                continue
            if b"vllm" in cmd.lower() and f"--port {port}".encode() in cmd:
                pids.append(pid)
    except OSError:
        pass
    return pids


def rss_gb(pid: int) -> float:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return float("nan")


def http_up(port: int, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def heal(name: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "models.sh"), "start", name],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def mem_guard() -> str:
    """调 models.sh mem-guard：available < 阈值时停 embed→fast，不停 big。返回其输出。"""
    r = subprocess.run(
        [str(ROOT / "scripts" / "models.sh"), "mem-guard"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return (r.stdout or r.stderr).strip()


def check_once(*, heal: bool, guard: bool = False) -> dict:
    state: dict = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "endpoints": {}, "mem_available_gb": None, "alarms": []}
    state["mem_available_gb"] = round(mem_available_gb(), 1)
    if state["mem_available_gb"] < MEM_LOW_ALARM_GB:
        state["alarms"].append(f"MEM_LOW {state['mem_available_gb']}GB < {MEM_LOW_ALARM_GB}GB")
    if guard and state["mem_available_gb"] < WATCHDOG_GUARD_GB:
        out = mem_guard()
        state["mem_guard"] = out
        state["alarms"].append(f"MEM_GUARD_TRIGGERED {state['mem_available_gb']}GB < {WATCHDOG_GUARD_GB}GB -> {out}")
    for ep in ENDPOINTS:
        name, port = ep["name"], ep["port"]
        up = http_up(port)
        pids = find_vllm_pids(port)
        rss = [round(rss_gb(p), 1) for p in pids]
        entry: dict = {"up": up, "pids": pids, "rss_gb": rss}
        state["endpoints"][name] = entry
        if not up:
            state["alarms"].append(f"{name}:800{port % 1000}_DOWN")
            if heal and ep["heal"]:
                heal(name)
                entry["healed"] = True
                state["alarms"].append(f"{name}_HEAL_ATTEMPT")
        for p, r in zip(pids, rss):
            if r > RSS_ALARM_GB:
                state["alarms"].append(f"{name}_RSS_HIGH pid={p} {r}GB > {RSS_ALARM_GB}GB")
    return state


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--heal", action="store_true", help="自动拉起挂掉的端点")
    ap.add_argument("--guard", action="store_true", help="内存看门：available < 阈值时停 embed→fast")
    ap.add_argument("--daemon", action="store_true", help="常驻循环模式")
    ap.add_argument("--interval", type=int, default=300, help="daemon 检查间隔秒")
    args = ap.parse_args()

    if args.daemon:
        while True:
            try:
                print(json.dumps(check_once(heal=args.heal, guard=args.guard), ensure_ascii=False), flush=True)
            except Exception as e:  # noqa: BLE001 — 看门狗永不因单次异常退出
                print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "error": str(e)}), flush=True)
            time.sleep(args.interval)
        return 0

    print(json.dumps(check_once(heal=args.heal, guard=args.guard), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
