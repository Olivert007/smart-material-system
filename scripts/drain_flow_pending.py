#!/usr/bin/env python3
"""Drain flow_pending: LLM suggest batches + optional high-confidence accept (meta only)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("SMS_API_BASE", "http://127.0.0.1:8010").rstrip("/")
OPS = os.environ.get("OPS_TOKEN", "dev-ops-token-change-me")


def _req(method: str, path: str, body: dict | None = None, timeout: float = 600) -> tuple[int, dict]:
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suggest-rounds", type=int, default=20)
    ap.add_argument("--suggest-limit", type=int, default=10)
    ap.add_argument("--accept-min-conf", type=float, default=0.85)
    ap.add_argument("--accept-limit", type=int, default=200)
    ap.add_argument("--no-accept", action="store_true")
    ap.add_argument("--force-role", default="", help="fast|big|empty")
    args = ap.parse_args()

    code, stats0 = _req("GET", "/api/v1/govern/flow/stats")
    print("stats_before", json.dumps({k: stats0.get(k) for k in ("pending", "pending_by_level", "published_total")}, ensure_ascii=False))

    suggest_summary = []
    for i in range(args.suggest_rounds):
        body: dict = {"limit": args.suggest_limit}
        if args.force_role in ("fast", "big"):
            body["force_role"] = args.force_role
        t0 = time.time()
        code, res = _req("POST", "/api/v1/govern/flow/suggest", body, timeout=900)
        dt = round(time.time() - t0, 1)
        processed = int(res.get("processed") or 0)
        suggest_summary.append(
            {
                "round": i + 1,
                "http": code,
                "processed": processed,
                "succeeded": res.get("succeeded"),
                "failed": res.get("failed"),
                "skipped": res.get("skipped"),
                "sec": dt,
            }
        )
        print("suggest", suggest_summary[-1])
        if processed == 0 or res.get("skipped"):
            break
        # stop early if nothing left
        if processed < args.suggest_limit:
            break

    accepted = 0
    accept_skip = 0
    if not args.no_accept:
        # page through pending and accept high-confidence L1/L2 with qty
        offset = 0
        while accepted < args.accept_limit:
            code, page = _req(
                "GET",
                f"/api/v1/govern/flow/pending?status=pending&limit=50&offset={offset}",
            )
            items = page.get("items") or []
            if not items:
                break
            for it in items:
                if accepted >= args.accept_limit:
                    break
                sug = it.get("suggested") or {}
                if it.get("llm_state") != "done":
                    accept_skip += 1
                    continue
                lvl = str(sug.get("parse_level") or it.get("parse_level") or "")
                conf = float(sug.get("confidence") or 0)
                qty = sug.get("quantity")
                if lvl not in ("L1", "L2") or conf < args.accept_min_conf or qty is None:
                    accept_skip += 1
                    continue
                code, out = _req(
                    "POST",
                    "/api/v1/govern/flow/confirm",
                    {
                        "pending_id": it["pending_id"],
                        "decision": "accept",
                        "note": f"cli-auto conf>={args.accept_min_conf}",
                    },
                )
                if code == 200 and out.get("ok"):
                    accepted += 1
                else:
                    accept_skip += 1
                    print("accept_fail", it["pending_id"], code, out)
            if len(items) < 50:
                break
            offset += 50

    code, stats1 = _req("GET", "/api/v1/govern/flow/stats")
    code, rec = _req("GET", "/api/v1/govern/flow/reconcile?persist=false")
    summary = {
        "suggest": suggest_summary,
        "accepted": accepted,
        "accept_skip": accept_skip,
        "stats_after": {
            k: stats1.get(k) for k in ("pending", "pending_by_level", "published_total", "l1_ratio")
        },
        "reconcile_total": rec.get("total"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "eval", "results")
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = os.path.join(out_dir, f"flow_pending_drain_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("wrote", path)
    print("FLOW_DRAIN_OK")


if __name__ == "__main__":
    main()
