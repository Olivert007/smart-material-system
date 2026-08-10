#!/usr/bin/env bash
# Multi-file harden: upload → stage(domain) → confirm → count rows.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${API:-http://127.0.0.1:8010}"
TOKEN="${OPS_TOKEN:-dev-ops-token-change-me}"
OUT="$ROOT/data/eval/results/file_harden_$(date -u +%Y%m%dT%H%M%SZ).json"
mkdir -p "$(dirname "$OUT")"

python3 - <<'PY' "$API" "$TOKEN" "$OUT"
import json, sys, time, urllib.request, urllib.error
from pathlib import Path

api, token, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
cases = [
    ("/workspace/2026-07/通信-溪洛渡川云公司CTGCY概览库存中的库存件 260721-95650(1).xlsx", "inventory"),
    ("/workspace/2026-07/通信部成都分部2026年备品备件定额调整清单---新新，发超哥(1).xlsx", "inventory"),
    ("/workspace/2026-07/副本 2026年维护材料需求统计（1月） (305 - CYPC-305-000320-2026 - 1 - A) - 1(2)(1).xlsx", "demand"),
    ("/workspace/2026-07/2026年通信部成都分部资产清查汇总表（成、溪、向）初稿(1).xlsx", "asset"),
]

def req(method, url, data=None, headers=None, files=None):
    h = {"X-Ops-Token": token, "X-Request-ID": f"harden_{int(time.time()*1000)}"}
    if headers: h.update(headers)
    body = None
    if files:
        import uuid
        boundary = uuid.uuid4().hex
        path, filename = files
        raw = Path(path).read_bytes()
        parts = []
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode())
        parts.append(raw)
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        body = b"".join(parts)
        h["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=600) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": str(e)}

results = []
for path, domain in cases:
    p = Path(path)
    item = {"file": p.name, "domain": domain, "ok": False}
    if not p.exists():
        item["error"] = "missing"; results.append(item); continue
    st, up = req("POST", f"{api}/api/v1/files", files=(str(p), p.name))
    item["upload_status"] = st
    item["file_id"] = up.get("file_id")
    task = up.get("task_id")
    if task:
        for _ in range(180):
            _, t = req("GET", f"{api}/api/v1/tasks/{task}")
            if t.get("status") in ("done", "failed"):
                item["task"] = t.get("status"); break
            time.sleep(0.5)
        if item.get("task") != "done":
            item["error"] = "task_failed"; results.append(item); continue
    st, sg = req("POST", f"{api}/api/v1/intake/stage/{item['file_id']}", {"config_version":"v1","target_domain":domain})
    item["stage_status"] = st
    item["staging"] = {k: sg.get(k) for k in ("status","version","clean_rows")}
    item["column_mapping"] = (sg.get("dry_run") or {}).get("column_mapping")
    if sg.get("status") != "STAGED":
        # try continue if already released with rows
        item["error"] = f"not_staged:{sg.get('status')}"; results.append(item); continue
    st, cf = req(
        "POST",
        f"{api}/api/v1/intake/stage/{item['file_id']}/confirm",
        {"version": sg.get("version"), "expected_status": "STAGED"},
        headers={"Idempotency-Key": f"harden-{item['file_id']}-{domain}"},
    )
    item["confirm_status"] = st
    item["rows"] = cf.get("rows")
    item["target_table"] = cf.get("target_table")
    item["release_id"] = (cf.get("release") or {}).get("release_id")
    item["ok"] = st == 200 and int(cf.get("rows") or 0) > 0
    results.append(item)
    print(json.dumps(item, ensure_ascii=False))

# biz counts
st, q = req("POST", f"{api}/api/v1/query", {
    "sql": "SELECT 'fact_inventory' t, COUNT(*) c FROM fact_inventory UNION ALL SELECT 'fact_asset', COUNT(*) FROM fact_asset UNION ALL SELECT 'fact_demand', COUNT(*) FROM fact_demand"
})
summary = {
    "ok_cases": sum(1 for r in results if r.get("ok")),
    "total_cases": len(results),
    "results": results,
    "counts": q.get("data") if st == 200 else q,
}
out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote", out)
print("HARDEN_OK" if summary["ok_cases"] == summary["total_cases"] else "HARDEN_CHECK")
PY
