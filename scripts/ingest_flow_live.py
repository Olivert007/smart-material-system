#!/usr/bin/env python3
"""Live 305B+ZW → fact_stock_flow via running F2 API (docs/12; plan 1B).

Unlike harden_flow_real.py this does NOT swap DATA_DIR — it targets the
already-running API on LOOPBACK (default http://127.0.0.1:8010).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    Path("/workspace/2026-07/305-CYPC-305-002362-2026-1-B-1.XLSX"),
    Path("/workspace/2026-07/通信部成都区域ZW物资汇总表 (新模板单独）.xlsx"),
]
BASE = os.environ.get("SMS_API_BASE", "http://127.0.0.1:8010").rstrip("/")
OPS = os.environ.get("OPS_TOKEN", "dev-ops-token-change-me")
EXPECT_SHEETS = {"低值易耗", "维护材料", "备品备件", "成都区域ZW物资台账（新模板）"}


def _req(
    method: str,
    path: str,
    *,
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: float = 120,
) -> tuple[int, dict | list | str]:
    url = path if path.startswith("http") else f"{BASE}{path}"
    h = dict(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            code = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        code = e.code
    if not raw:
        return code, {}
    try:
        return code, json.loads(raw)
    except json.JSONDecodeError:
        return code, raw


def _multipart(path: Path) -> tuple[bytes, str]:
    boundary = "----SmsLiveBoundary7f3a"
    name = path.name
    body = path.read_bytes()
    ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    parts = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode(),
        body,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _wait_task(task_id: str | None, timeout: float = 900) -> dict:
    if not task_id:
        return {"status": "done"}
    t0 = time.time()
    last: dict = {}
    while time.time() - t0 < timeout:
        code, last = _req("GET", f"/api/v1/tasks/{task_id}")
        if not isinstance(last, dict):
            raise RuntimeError(f"bad task body: {last}")
        if last.get("status") in ("done", "failed"):
            return last
        time.sleep(1.0)
    return last


def _ingest_one(path: Path) -> dict:
    item: dict = {"file": path.name, "ok": False}
    payload, ctype = _multipart(path)
    code, body = _req(
        "POST",
        "/api/v1/files",
        data=payload,
        headers={"Content-Type": ctype},
        timeout=300,
    )
    item["upload_status"] = code
    if code not in (200, 202) or not isinstance(body, dict):
        item["upload_body"] = body
        return item
    file_id = body["file_id"]
    task_id = body.get("task_id")
    item["file_id"] = file_id
    item["reused"] = body.get("reused")
    t = _wait_task(task_id)
    item["task"] = t.get("status")
    if t.get("status") != "done":
        item["task_body"] = t
        return item

    code, stg = _req(
        "POST",
        f"/api/v1/intake/stage/{file_id}",
        data=json.dumps({"config_version": "v1", "target_domain": "stock_flow"}).encode(),
        headers={"Content-Type": "application/json"},
        timeout=600,
    )
    item["stage_status"] = code
    if not isinstance(stg, dict):
        item["stage_body"] = stg
        return item
    item["staging"] = {k: stg.get(k) for k in ("status", "version", "clean_rows")}
    item["flow_parse"] = (stg.get("dry_run") or {}).get("flow_parse")
    item["flow_pending"] = (stg.get("dry_run") or {}).get("flow_pending")
    if stg.get("status") != "STAGED" or int(stg.get("clean_rows") or 0) < 1:
        item["stage_body"] = {k: stg.get(k) for k in ("status", "error", "message", "dry_run")}
        return item

    code, cf = _req(
        "POST",
        f"/api/v1/intake/stage/{file_id}/confirm",
        data=json.dumps({"version": stg["version"], "expected_status": "STAGED"}).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Ops-Token": OPS,
            "Idempotency-Key": f"live-flow-{file_id}-{stg['version']}",
        },
        timeout=300,
    )
    item["confirm_status"] = code
    if not isinstance(cf, dict) or code != 200:
        item["confirm_body"] = cf
        return item
    item["rows"] = cf.get("rows")
    item["target_table"] = cf.get("target_table")
    item["release_id"] = (cf.get("release") or {}).get("release_id")
    item["idempotent"] = cf.get("idempotent")
    item["ok"] = cf.get("target_table") == "fact_stock_flow" and int(cf.get("rows") or 0) >= 1
    return item


def main() -> None:
    missing = [str(p) for p in SAMPLES if not p.exists()]
    if missing:
        raise SystemExit(f"sample missing: {missing}")
    code, ready = _req("GET", "/health/ready")
    if code != 200 or not isinstance(ready, dict) or ready.get("status") != "ready":
        raise SystemExit(f"API not ready: {code} {ready}")

    # Preflight loader (local, does not write)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DATA_DIR", str(ROOT / "data"))
    from app.services.intake.evidence import load_stock_flow_tabular  # noqa: E402

    pre = {}
    for p in SAMPLES:
        df = load_stock_flow_tabular(p)
        sheets = sorted(df["sheet"].dropna().unique().tolist()) if len(df) and "sheet" in df.columns else []
        pre[p.name] = {"rows": int(len(df)), "sheets": sheets}
        print("preflight", p.name, pre[p.name])
        assert len(df) > 0, p

    results = []
    for p in SAMPLES:
        print("ingest", p.name, "…")
        item = _ingest_one(p)
        results.append(item)
        print(json.dumps(item, ensure_ascii=False))
        if not item.get("ok"):
            raise SystemExit(f"INGEST_FAILED {p.name}")

    code, stats = _req("GET", "/api/v1/govern/flow/stats")
    code2, aud = _req(
        "GET",
        "/api/v1/govern/flow/audit?limit=5000",
        headers={"X-Ops-Token": OPS},
    )
    code3, gate = _req("GET", "/api/v1/govern/flow/gate")
    if not isinstance(stats, dict) or not isinstance(aud, dict) or not isinstance(gate, dict):
        raise SystemExit("post-check failed")

    year_qty = sum(
        1
        for s in aud.get("suspicious") or []
        if "year_as_quantity" in (s.get("reasons") or [])
    )
    sheets = sorted(
        {
            r.get("source_sheet")
            for r in stats.get("by_source_sheet") or []
            if r.get("source_sheet")
        }
    )
    summary = {
        "ok_cases": sum(1 for r in results if r.get("ok")),
        "total_cases": len(results),
        "preflight": pre,
        "results": results,
        "stats": {
            "published_by_level": stats.get("published_by_level"),
            "published_total": stats.get("published_total"),
            "l1_ratio": stats.get("l1_ratio"),
            "pending": stats.get("pending"),
            "by_source_sheet": stats.get("by_source_sheet"),
        },
        "sheets": sheets,
        "year_as_quantity": year_qty,
        "gate_ready": gate.get("ready"),
        "gate_missing": gate.get("missing"),
    }
    out = ROOT / "data" / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = out / f"flow_live_{stamp}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("wrote", path)
    print(
        "sheets",
        sheets,
        "L1/L2/L3",
        stats.get("published_by_level"),
        "published",
        stats.get("published_total"),
        "pending",
        stats.get("pending"),
        "year_qty",
        year_qty,
        "gate",
        gate.get("ready"),
    )
    assert summary["ok_cases"] == summary["total_cases"]
    assert year_qty == 0, year_qty
    assert int(stats.get("published_total") or 0) >= 400, stats.get("published_total")
    assert EXPECT_SHEETS <= set(sheets), sheets
    assert gate.get("ready") is True, gate.get("missing")
    print("FLOW_LIVE_OK")


if __name__ == "__main__":
    main()
