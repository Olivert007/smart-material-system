#!/usr/bin/env python3
"""A6 smoke: plant year-as-qty → audit → lineage rebuild → clean (docs/12 FL7)."""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "sandboxes" / "test_flow_a6"
if TEST_DATA.exists():
    shutil.rmtree(TEST_DATA)
os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.2"

# Guard: lineage must never UPDATE quantity in place (impl lives in govern/ after A0-1 split;
# app/services/flow_lineage.py is a re-export shim and carries none of the SQL).
src = (ROOT / "app/services/govern/flow_lineage.py").read_text(encoding="utf-8")
assert not re.search(r"UPDATE\s+fact_stock_flow\s+SET\s+quantity", src, re.I), "FL7 violate"
assert "DELETE FROM fact_stock_flow" in src

from app.main import app  # noqa: E402
from app.repositories import writer_conn  # noqa: E402


CSV = """物资编码,物资名称,单位,入库记录,入库数量,出库记录,出库数量
M001,光纤跳线,条,2025年6月，张停伟入库4包；2026年6月，李茜入库6包,10,2026.1.6/李茜/会议室搭建备用使用,1
M002,光模块,个,2022-08-17 00:00:00,2,已使用,
"""


def main() -> None:
    headers = {"X-Ops-Token": "test-ops"}
    with TestClient(app) as client:
        p = TEST_DATA / "flow.csv"
        p.write_text(CSV, encoding="utf-8")
        with p.open("rb") as f:
            r = client.post("/api/v1/files", files={"file": ("flow_a6.csv", f, "text/csv")})
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
        rel = c.json()
        release_id = (rel.get("release") or {}).get("release_id") or rel.get("release_id")
        assert release_id, rel
        clean_before = int(rel["rows"])
        print("released", release_id, "rows", clean_before)

        # Plant historical year-as-qty bug (simulate legacy bad write)
        con = writer_conn()
        try:
            con.execute(
                """
                INSERT INTO fact_stock_flow (
                    flow_id, material_id, flow_type, flow_date, quantity, unit,
                    person, purpose, remark, parse_level, parse_source,
                    source_file, source_sheet, source_row, source_segment,
                    source_release_id
                ) VALUES (?, ?, 'IN', NULL, 2023, '', NULL, NULL, '2023年', NULL, 'legacy',
                          'planted', 'Sheet1', 99, 0, ?)
                """,
                [f"bad_{release_id}", "mat_plant", release_id],
            )
        finally:
            con.close()

        aud = client.get("/api/v1/govern/flow/audit", headers=headers)
        assert aud.status_code == 200, aud.text
        body = aud.json()
        print("audit_before", body.get("suspicious_count"), body.get("by_release"))
        assert body["ok"] and body["suspicious_count"] >= 1
        year_hits = [
            s for s in body["suspicious"] if "year_as_quantity" in (s.get("reasons") or [])
        ]
        assert any(s.get("source_release_id") == release_id for s in year_hits), year_hits

        reb = client.post(
            "/api/v1/govern/flow/rebuild",
            headers=headers,
            json={"release_id": release_id},
        )
        assert reb.status_code == 200, reb.text
        rb = reb.json()
        print("rebuild", {k: rb.get(k) for k in (
            "deleted_flows", "inserted", "clean_of_year_qty", "post_audit_year_qty"
        )})
        assert rb["ok"]
        assert rb["deleted_flows"] >= clean_before + 1
        assert rb["inserted"] == clean_before
        assert rb["clean_of_year_qty"] is True

        aud2 = client.get("/api/v1/govern/flow/audit", headers=headers).json()
        year_left = [
            s
            for s in aud2.get("suspicious") or []
            if s.get("source_release_id") == release_id
            and "year_as_quantity" in (s.get("reasons") or [])
        ]
        assert not year_left, year_left
        print("FLOW_A6_OK")


if __name__ == "__main__":
    main()
