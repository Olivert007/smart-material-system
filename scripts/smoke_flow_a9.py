#!/usr/bin/env python3
"""A9 smoke: FLOW_* metrics stay draft; L1/L2/L3 stats + baseline values."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "sandboxes" / "test_flow_a9"
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
            r = client.post("/api/v1/files", files={"file": ("flow_a9.csv", f, "text/csv")})
        assert r.status_code == 202, r.text
        file_id, task_id = r.json()["file_id"], r.json()["task_id"]
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
        c = client.post(
            f"/api/v1/intake/stage/{file_id}/confirm",
            headers=headers,
            json={"version": stg["version"], "expected_status": "STAGED"},
        )
        assert c.status_code == 200, c.text

        stats = client.get("/api/v1/govern/flow/stats").json()
        print("stats", {
            k: stats.get(k)
            for k in ("published_by_level", "published_total", "l1_ratio", "l1_over_l1l2", "pending")
        })
        assert stats["published_total"] >= 1
        assert "by_source_file" in stats and "by_source_sheet" in stats

        mets = client.get("/api/v1/metrics").json()
        flow = [i for i in mets["items"] if i["metric_id"].startswith("FLOW_")]
        assert {i["metric_id"] for i in flow} >= {
            "FLOW_QTY_TOTAL",
            "FLOW_PARSE_L1_RATIO",
            "FLOW_RECONCILE_GAP_CNT",
        }
        assert all(i["status"] == "draft" for i in flow), flow

        # force-activate must be blocked
        bad = client.post(
            "/api/v1/metrics",
            headers=headers,
            json={
                "metric_id": "FLOW_QTY_TOTAL",
                "metric_name": "流水入库合计（质量门）",
                "definition_sql": "SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='IN'",
                "status": "active",
            },
        )
        assert bad.status_code == 403, bad.text
        assert bad.json().get("code") == "FLOW_GATE"

        for mid in ("FLOW_QTY_TOTAL", "FLOW_PARSE_L1_RATIO", "FLOW_RECONCILE_GAP_CNT"):
            ev = client.post(f"/api/v1/metrics/{mid}/evaluate").json()
            print("eval", mid, ev.get("value"), ev.get("status"), ev.get("note"))
            assert ev["status"] == "draft"
            assert ev.get("active") is False

        base = client.get("/api/v1/govern/flow/baseline").json()
        assert base["ok"] and base["flow_metrics_all_draft"]
        out = TEST_DATA / "flow_baseline.json"
        out.write_text(json.dumps(base, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("wrote", out)
        print("gate.missing", base["gate"]["missing"])
        print("FLOW_A9_OK")


if __name__ == "__main__":
    main()
