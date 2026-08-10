# -*- coding: utf-8 -*-
"""Run one real Excel/CSV through Phase A trusted pipeline."""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "samples"
RUN_DIR = ROOT / "tests" / "sandboxes" / "real_sample_run"

# Prefer small real workbook from workspace parent
CANDIDATES = [
    Path("/workspace/2026-07/通信-溪洛渡川云公司CTGCY概览库存中的库存件 260721-95650(1).xlsx"),
    Path("/workspace/2026-07/通信部成都分部2026年备品备件定额调整清单---新新，发超哥(1).xlsx"),
]


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else next((p for p in CANDIDATES if p.exists()), None)
    if not src or not src.exists():
        raise SystemExit("no sample file found; pass a path")

    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    dest = SAMPLE_DIR / src.name
    if not dest.exists():
        shutil.copy2(src, dest)

    os.environ["DATA_DIR"] = str(RUN_DIR)
    os.environ["OPS_TOKEN"] = "test-ops"
    os.environ["ALLOW_FREE_QUERY"] = "1"
    os.environ["WORKER_POLL_SEC"] = "0.3"
    os.environ["SPARSE_EVIDENCE_ROWS"] = "2000"

    from app.main import app  # noqa: WPS433

    headers = {"X-Ops-Token": "test-ops"}
    with TestClient(app) as client:
        with dest.open("rb") as f:
            r = client.post("/api/v1/files", files={"file": (dest.name, f, "application/octet-stream")})
        assert r.status_code == 202, r.text
        body = r.json()
        file_id, task_id = body["file_id"], body["task_id"]
        print("uploaded", body)

        for _ in range(120):
            t = client.get(f"/api/v1/tasks/{task_id}").json()
            if t["status"] in ("done", "failed"):
                break
            time.sleep(0.5)
        print("task", t)
        assert t["status"] == "done", t

        s = client.post(
            f"/api/v1/intake/stage/{file_id}",
            json={"config_version": "v1", "target_domain": "inventory"},
        )
        assert s.status_code == 200, s.text
        print("staging", {k: s.json().get(k) for k in ("status", "clean_rows", "fingerprint")})
        print("dry_run", s.json().get("dry_run"))

        c = client.post(f"/api/v1/intake/stage/{file_id}/confirm", headers=headers)
        assert c.status_code == 200, c.text
        print("release", c.json())

        q = client.post(
            "/api/v1/query",
            headers=headers,
            json={
                "sql": "SELECT material_id, region, category, stock_qty, unit, location "
                "FROM fact_inventory ORDER BY inventory_id LIMIT 5"
            },
        )
        assert q.status_code == 200, q.text
        print("preview", q.json())
        print("REAL_SAMPLE_OK", dest.name)


if __name__ == "__main__":
    main()
