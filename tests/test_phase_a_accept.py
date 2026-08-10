# -*- coding: utf-8 -*-
"""Phase A acceptance: idempotent confirm + RELEASING compensation."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "sandboxes" / "test_accept"
if TEST_DATA.exists():
    shutil.rmtree(TEST_DATA)
os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.2"

from app.main import app  # noqa: E402
from app.repositories import meta_tx  # noqa: E402
from app.services.writer import compensate_releasing  # noqa: E402


def _wait_task(client: TestClient, task_id: str) -> dict:
    for _ in range(50):
        t = client.get(f"/api/v1/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            return t
        time.sleep(0.2)
    raise AssertionError("task timeout")


def _upload_stage(client: TestClient, name: str, content: str) -> str:
    p = TEST_DATA / name
    p.write_text(content, encoding="utf-8")
    with p.open("rb") as f:
        r = client.post("/api/v1/files", files={"file": (name, f, "text/csv")})
    assert r.status_code == 202, r.text
    body = r.json()
    assert _wait_task(client, body["task_id"])["status"] == "done"
    s = client.post(
        f"/api/v1/intake/stage/{body['file_id']}",
        json={"config_version": "v1", "target_domain": "inventory"},
    )
    assert s.status_code == 200, s.text
    return body["file_id"]


def main() -> None:
    headers = {"X-Ops-Token": "test-ops"}
    with TestClient(app) as client:
        file_id = _upload_stage(client, "inv.csv", "物资名称,数量,单位\n光纤跳线,12,条\n光模块,4,个\n")

        r1 = client.post(f"/api/v1/intake/stage/{file_id}/confirm", headers=headers)
        assert r1.status_code == 200, r1.text
        rel = r1.json()["release"]["release_id"]
        assert r1.json()["target_table"] == "fact_inventory"

        # duplicate confirm → idempotent, same release
        r2 = client.post(f"/api/v1/intake/stage/{file_id}/confirm", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["idempotent"] is True
        assert r2.json()["release"]["release_id"] == rel

        q = client.post(
            "/api/v1/query",
            headers=headers,
            json={"sql": f"SELECT COUNT(*) AS c FROM fact_inventory WHERE source_release_id='{rel}'"},
        )
        assert q.status_code == 200, q.text
        c1 = q.json()["data"][0]["c"]
        assert c1 == 2, c1

        # simulate crash: mark RELEASING again with same release_id and re-run compensate
        with meta_tx() as con:
            con.execute(
                "UPDATE staging_record SET status='RELEASING' WHERE release_id=?",
                [rel],
            )
        compensate_releasing()
        q2 = client.post(
            "/api/v1/query",
            headers=headers,
            json={"sql": f"SELECT COUNT(*) AS c FROM fact_inventory WHERE source_release_id='{rel}'"},
        )
        c2 = q2.json()["data"][0]["c"]
        assert c2 == c1, (c1, c2)

        # second file should not collide
        file_id2 = _upload_stage(client, "inv2.csv", "name,qty\n电缆,1\n")
        r3 = client.post(f"/api/v1/intake/stage/{file_id2}/confirm", headers=headers)
        assert r3.status_code == 200, r3.text
        total = client.post(
            "/api/v1/query",
            headers=headers,
            json={"sql": "SELECT COUNT(*) AS c FROM fact_inventory"},
        ).json()["data"][0]["c"]
        assert total == 3, total

        print("PHASE_A_ACCEPT_OK", {"release": rel, "rows": c1, "total": total})


if __name__ == "__main__":
    main()
