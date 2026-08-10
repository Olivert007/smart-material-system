# -*- coding: utf-8 -*-
"""Phase A smoke: upload → evidence → stage → confirm → query."""
from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

# Isolate test data — wipe before importing app (config mkdir on import)
ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "sandboxes" / "test_run"
if TEST_DATA.exists():
    import shutil

    shutil.rmtree(TEST_DATA)
os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.2"

from app.main import app  # noqa: E402


def main() -> None:
    with TestClient(app) as client:
        assert client.get("/health/live").json()["status"] == "live"

        csv_path = TEST_DATA / "sample.csv"
        csv_path.write_text("物资名称,数量,单位\n电缆,10,米\n光模块,3,个\n", encoding="utf-8")

        with csv_path.open("rb") as f:
            r = client.post("/api/v1/files", files={"file": ("sample.csv", f, "text/csv")})
        assert r.status_code == 202, r.text
        body = r.json()
        file_id = body["file_id"]
        task_id = body["task_id"]
        assert task_id

        # wait worker
        for _ in range(50):
            t = client.get(f"/api/v1/tasks/{task_id}").json()
            if t["status"] in ("done", "failed"):
                break
            time.sleep(0.2)
        assert t["status"] == "done", t

        s = client.post(
            f"/api/v1/intake/stage/{file_id}",
            json={"config_version": "v1", "target_domain": "inventory"},
        )
        assert s.status_code == 200, s.text
        staging = s.json()
        assert staging["status"] == "STAGED"

        # confirm without token → 401
        bad = client.post(f"/api/v1/intake/stage/{file_id}/confirm")
        assert bad.status_code == 401

        ok = client.post(
            f"/api/v1/intake/stage/{file_id}/confirm",
            headers={"X-Ops-Token": "test-ops"},
        )
        assert ok.status_code == 200, ok.text
        rel = ok.json()
        assert rel["status"] == "RELEASED"

        # idempotent confirm
        ok2 = client.post(
            f"/api/v1/intake/stage/{file_id}/confirm",
            headers={"X-Ops-Token": "test-ops"},
        )
        assert ok2.status_code == 200
        assert ok2.json().get("idempotent") is True

        q = client.post(
            "/api/v1/query",
            headers={"X-Ops-Token": "test-ops"},
            json={"sql": "SELECT COUNT(*) AS c FROM fact_inventory"},
        )
        assert q.status_code == 200, q.text
        assert q.json()["data"][0]["c"] > 0

        # AST reject write
        bad_sql = client.post(
            "/api/v1/query",
            headers={"X-Ops-Token": "test-ops"},
            json={"sql": "DELETE FROM fact_inventory"},
        )
        assert bad_sql.status_code == 400

        b = client.post("/api/v1/ops/backup", headers={"X-Ops-Token": "test-ops"})
        assert b.status_code == 200, b.text
        print(
            "PHASE_A_SMOKE_OK",
            {
                "file_id": file_id,
                "release": rel["release"]["release_id"],
                "rows": q.json()["data"][0]["c"],
                "target_table": rel.get("target_table"),
            },
        )


if __name__ == "__main__":
    main()
