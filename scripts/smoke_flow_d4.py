#!/usr/bin/env python3
"""D4 smoke: metric fixtures + gate + activate FLOW_* (docs/08/12)."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "sandboxes" / "test_flow_d4"
if TEST_DATA.exists():
    shutil.rmtree(TEST_DATA)
os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.2"
os.environ["FLOW_LLM_ENABLED"] = "0"

from app.main import app  # noqa: E402
from app.services.metric_fixtures import run_metric_fixtures  # noqa: E402

CSV = """物资编码,物资名称,单位,入库记录,入库数量,出库记录,出库数量
M001,光纤跳线,条,2025年6月，张停伟入库4包；2026年6月，李茜入库6包,10,2026.1.6/李茜/会议室搭建备用使用,1
M002,光模块,个,2022-08-17 00:00:00,2,已使用,
"""


def main() -> None:
    fx = run_metric_fixtures()
    assert fx["ok"], fx
    print("FIXTURES_OK", fx["passed"], "/", fx["total"])

    headers = {"X-Ops-Token": "test-ops"}
    with TestClient(app) as client:
        # fixtures API
        r = client.get("/api/v1/metrics/fixtures")
        assert r.status_code == 200 and r.json().get("ok"), r.text

        # publish stock_flow so gate has published rows
        p = TEST_DATA / "flow.csv"
        p.write_text(CSV, encoding="utf-8")
        with p.open("rb") as f:
            up = client.post("/api/v1/files", files={"file": ("flow_d4.csv", f, "text/csv")})
        assert up.status_code == 202, up.text
        file_id, task_id = up.json()["file_id"], up.json()["task_id"]
        # Drain parse task (worker may be busy); claim+process is idempotent with status checks
        from app.services.intake import claim_next_task, process_parse_evidence

        for _ in range(80):
            t = client.get(f"/api/v1/tasks/{task_id}").json()
            if t["status"] in ("done", "failed"):
                break
            claimed = claim_next_task()
            if claimed:
                process_parse_evidence(claimed)
            else:
                time.sleep(0.15)
        assert t["status"] == "done", t
        stg = client.post(
            f"/api/v1/intake/stage/{file_id}",
            json={"config_version": "v1", "target_domain": "stock_flow"},
        ).json()
        assert stg["status"] == "STAGED", stg
        cf = client.post(
            f"/api/v1/intake/stage/{file_id}/confirm",
            headers=headers,
            json={"version": stg["version"], "expected_status": "STAGED"},
        )
        assert cf.status_code == 200, cf.text

        gate = client.get("/api/v1/govern/flow/gate").json()
        print("gate", json.dumps(gate.get("checks"), ensure_ascii=False), "missing", gate.get("missing"))
        assert gate.get("ready"), gate

        # activate
        act = client.post("/api/v1/metrics/flow/activate", headers=headers, json={})
        assert act.status_code == 200, act.text
        body = act.json()
        assert body.get("ok")
        ids = {x["metric_id"] for x in body.get("activated") or []}
        assert "FLOW_QTY_TOTAL" in ids, body

        # verify active + evaluate
        m = client.get("/api/v1/metrics/FLOW_QTY_TOTAL").json()
        assert m["status"] == "active", m
        ev = client.post("/api/v1/metrics/FLOW_QTY_TOTAL/evaluate").json()
        assert ev["active"] is True and ev["status"] == "active"
        assert ev.get("note") in (None, "")
        print("FLOW_QTY_TOTAL", ev.get("value"), "status", ev.get("status"))

        # idempotent second activate
        act2 = client.post("/api/v1/metrics/flow/activate", headers=headers, json={})
        assert act2.status_code == 200
        assert all(x.get("idempotent") for x in act2.json().get("activated") or [])

        # restart seed must not demote
        from app.services.metrics import ensure_flow_metrics_draft, get_metric

        ensure_flow_metrics_draft()
        assert get_metric("FLOW_QTY_TOTAL")["status"] == "active"

        print("FLOW_D4_OK")


if __name__ == "__main__":
    main()
