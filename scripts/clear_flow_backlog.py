#!/usr/bin/env python3
"""Clear flow_pending backlog with an explicit ops policy (docs/12).

Policy (default):
  - accept: llm done, qty present, conf >= --accept-min-conf, level L1|L2
            (overwrite=True on FLOW_EXAMPLE_CONFLICT)
  - ignore: L3, or no qty (do not invent quantities)
  - conflict queue (status=conflict): same rules; accept with overwrite

Does NOT publish to DuckDB fact_stock_flow — only flow_example + pending status.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("SMS_API_BASE", "http://127.0.0.1:8010").rstrip("/")
OPS = os.environ.get("OPS_TOKEN", "dev-ops-token-change-me")


def _req(method: str, path: str, body: dict | None = None, timeout: float = 300) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"X-Ops-Token": OPS, "Content-Type": "application/json"}
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw}


def _fetch_all(status: str) -> list[dict]:
    items: list[dict] = []
    offset = 0
    while True:
        code, page = _req("GET", f"/api/v1/govern/flow/pending?status={status}&limit=100&offset={offset}")
        if code != 200:
            raise RuntimeError(f"list pending failed: {code} {page}")
        batch = page.get("items") or []
        items.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    return items


def _decide(it: dict, min_conf: float) -> tuple[str, str, bool]:
    sug = it.get("suggested") or {}
    qty = sug.get("quantity")
    conf = float(sug.get("confidence") or 0)
    lvl = str(sug.get("parse_level") or it.get("parse_level") or "")
    llm = it.get("llm_state")
    if llm == "done" and qty is not None and conf >= min_conf and lvl in ("L1", "L2"):
        return "accept", f"backlog-clear conf={conf:.2f} qty={qty}", True
    return "ignore", "backlog-clear no_qty_or_L3_or_low_conf", False


def _confirm(pending_id: str, decision: str, note: str, overwrite: bool) -> tuple[bool, dict]:
    code, out = _req(
        "POST",
        "/api/v1/govern/flow/confirm",
        {"pending_id": pending_id, "decision": decision, "note": note, "overwrite": overwrite},
    )
    if code == 200 and out.get("ok"):
        return True, out
    if decision == "accept" and (out.get("conflict") or out.get("code") == "FLOW_EXAMPLE_CONFLICT"):
        code2, out2 = _req(
            "POST",
            "/api/v1/govern/flow/confirm",
            {
                "pending_id": pending_id,
                "decision": "accept",
                "note": note + " +overwrite",
                "overwrite": True,
            },
        )
        if code2 == 200 and out2.get("ok"):
            return True, out2
        code3, out3 = _req(
            "POST",
            "/api/v1/govern/flow/confirm",
            {"pending_id": pending_id, "decision": "ignore", "note": "backlog-clear conflict fallback ignore"},
        )
        return bool(code3 == 200 and out3.get("ok")), out3
    return False, out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accept-min-conf", type=float, default=0.6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    counts = {"accepted": 0, "ignored": 0, "failed": 0}
    for status in ("pending", "conflict"):
        items = _fetch_all(status)
        print(f"{status}_before", len(items))
        for it in items:
            decision, note, overwrite = _decide(it, args.accept_min_conf)
            if args.dry_run:
                counts["accepted" if decision == "accept" else "ignored"] += 1
                continue
            ok, out = _confirm(it["pending_id"], decision, note, overwrite)
            if ok:
                counts["accepted" if decision == "accept" else "ignored"] += 1
            else:
                counts["failed"] += 1
                print("fail", it["pending_id"], out)

    code, stats = _req("GET", "/api/v1/govern/flow/stats")
    code, pp = _req("GET", "/api/v1/govern/flow/pending?status=pending&limit=1")
    code, cp = _req("GET", "/api/v1/govern/flow/pending?status=conflict&limit=1")
    summary = {
        **counts,
        "dry_run": args.dry_run,
        "accept_min_conf": args.accept_min_conf,
        "stats": {k: stats.get(k) for k in ("pending", "pending_by_level", "published_total", "l1_ratio")},
        "pending_total": pp.get("total"),
        "conflict_total": cp.get("total"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    out_dir = Path(__file__).resolve().parents[1] / "data" / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"flow_backlog_clear_{ts}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path)
    sys.exit(1 if counts["failed"] else 0)


if __name__ == "__main__":
    main()
