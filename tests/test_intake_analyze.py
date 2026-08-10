# -*- coding: utf-8 -*-
"""P1-1: intake analyze orchestration Step1–4 (+ optional stage)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_analyze_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.15"
os.environ["INTAKE_GATE_ENFORCE"] = "1"
os.environ["INTAKE_REQUIRE_PLAN_CONFIRM"] = "0"
os.environ["EMBED_FALLBACK_LEXICAL"] = "1"

sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _wait_task(client: TestClient, task_id: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = client.get(f"/api/v1/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            return t
        time.sleep(0.15)
    raise AssertionError(f"task timeout: {task_id}")


def test_analyze_then_release() -> None:
    headers = {"X-Ops-Token": "test-ops"}
    csv_path = TMP / "inv_analyze.csv"
    csv_path.write_text(
        "物资编码,物资名称,现有数量,单位,区域\n"
        "A001,光纤跳线,12,条,东区\n"
        "A002,光模块,4,个,西区\n",
        encoding="utf-8",
    )
    with TestClient(app) as client:
        with csv_path.open("rb") as f:
            up = client.post("/api/v1/files", files={"file": ("inv_analyze.csv", f, "text/csv")})
        assert up.status_code == 202, up.text
        body = up.json()
        fid = body["file_id"]
        assert _wait_task(client, body["task_id"])["status"] == "done"

        an = client.post(
            f"/api/v1/intake/analyze/{fid}",
            json={
                "target_domain": "inventory",
                "include_stage": True,
                "refresh_profile": False,
            },
        )
        assert an.status_code == 200, an.text
        payload = an.json()
        assert payload["ok"] is True, payload
        assert payload["steps"]["step1_profile"]["ok"] is True
        assert payload["steps"]["step3_quality"]["ok"] is True
        assert payload["steps"]["step4_plan"]["ok"] is True
        assert payload["steps"]["stage"]["ok"] is True
        assert payload["steps"]["stage"]["status"] in ("STAGED", "RELEASED")

        bundle = client.get(f"/api/v1/intake/report/{fid}")
        assert bundle.status_code == 200, bundle.text
        b = bundle.json()
        assert b["profile"] is not None
        assert b["quality"] is not None
        assert b["plan"] is not None
        assert b["analyze"] is not None
        assert b["staging"] is not None

        conf = client.post(
            f"/api/v1/intake/stage/{fid}/confirm",
            headers=headers,
            json={"expected_status": "STAGED", "force": False},
        )
        assert conf.status_code == 200, conf.text
        rel = conf.json()["release"]["release_id"]
        assert conf.json()["target_table"] == "fact_inventory"

        q = client.post(
            "/api/v1/query",
            headers=headers,
            json={
                "sql": (
                    "SELECT COUNT(*) AS c FROM fact_inventory "
                    f"WHERE source_release_id='{rel}'"
                )
            },
        )
        assert q.status_code == 200, q.text
        assert q.json()["data"][0]["c"] == 2


def test_analyze_not_ready() -> None:
    with TestClient(app) as client:
        r = client.post("/api/v1/intake/analyze/no_such_file")
        assert r.status_code == 404


def main() -> None:
    test_analyze_not_ready()
    print("OK not_ready")
    test_analyze_then_release()
    print("OK analyze_then_release")
    print("INTAKE_ANALYZE_OK")


if __name__ == "__main__":
    main()
