# -*- coding: utf-8 -*-
"""Module 12 A-规则 smoke: stock_flow staging → confirm → query + pending."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "sandboxes" / "test_flow"
if TEST_DATA.exists():
    shutil.rmtree(TEST_DATA)
os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.2"

from app.main import app  # noqa: E402


CSV = """物资编码,物资名称,单位,入库记录,入库数量,出库记录,出库数量
M001,光纤跳线,条,2025年6月，张停伟入库4包；2026年6月，李茜入库6包,10,2026.1.6/李茜/会议室搭建备用使用,1
M002,光模块,个,2022-08-17 00:00:00,2,已使用,
M003,标签机,台,2023年,1,2024.12.30 借用给宜昌分部,1
"""


def main() -> None:
    headers = {"X-Ops-Token": "test-ops"}
    with TestClient(app) as client:
        p = TEST_DATA / "flow.csv"
        p.write_text(CSV, encoding="utf-8")
        with p.open("rb") as f:
            r = client.post("/api/v1/files", files={"file": ("flow.csv", f, "text/csv")})
        assert r.status_code == 202, r.text
        body = r.json()
        file_id, task_id = body["file_id"], body["task_id"]
        for _ in range(50):
            t = client.get(f"/api/v1/tasks/{task_id}").json()
            if t["status"] in ("done", "failed"):
                break
            time.sleep(0.2)
        assert t["status"] == "done", t

        s = client.post(
            f"/api/v1/intake/stage/{file_id}",
            json={"config_version": "v1", "target_domain": "stock_flow"},
        )
        assert s.status_code == 200, s.text
        stg = s.json()
        print("staging", {k: stg.get(k) for k in ("status", "clean_rows", "version")})
        print("dry_run.flow", (stg.get("dry_run") or {}).get("flow_parse"), "pending", (stg.get("dry_run") or {}).get("flow_pending"))
        assert stg["status"] == "STAGED"
        assert stg["clean_rows"] >= 1, stg
        assert (stg.get("dry_run") or {}).get("flow_pending", 0) >= 1

        c = client.post(
            f"/api/v1/intake/stage/{file_id}/confirm",
            headers=headers,
            json={"version": stg["version"], "expected_status": "STAGED"},
        )
        assert c.status_code == 200, c.text
        print("release", {k: c.json().get(k) for k in ("status", "rows", "target_table")})
        assert c.json()["target_table"] == "fact_stock_flow"
        assert c.json()["rows"] >= 1

        q = client.post(
            "/api/v1/query",
            headers=headers,
            json={
                "sql": "SELECT flow_type, quantity, parse_level, person, remark FROM fact_stock_flow "
                "ORDER BY source_row, source_segment"
            },
        )
        assert q.status_code == 200, q.text
        data = q.json()["data"]
        print("flows", data)
        # no year-as-qty
        for row in data:
            assert row.get("quantity") not in (2023, 2024, 2025, 2026, 2023.0, 2024.0, 2025.0, 2026.0)

        pend = client.get("/api/v1/govern/flow/pending").json()
        print("pending_total", pend["total"])
        assert pend["total"] >= 1
        pid = pend["items"][0]["pending_id"]
        conf = client.post(
            "/api/v1/govern/flow/confirm",
            headers=headers,
            json={"pending_id": pid, "decision": "ignore", "note": "smoke"},
        )
        assert conf.status_code == 200, conf.text
        print("confirm", conf.json())

        stats = client.get("/api/v1/govern/flow/stats").json()
        print("stats", stats)
        rec = client.get("/api/v1/govern/flow/reconcile").json()
        print("reconcile_total", rec["total"])
        print("FLOW_SMOKE_OK")


if __name__ == "__main__":
    main()
