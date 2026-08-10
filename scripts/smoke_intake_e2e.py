#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E smoke: upload → analyze → stage confirm → query (INTAKE_E2E_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_intake_e2e_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.15"
os.environ["INTAKE_GATE_ENFORCE"] = "1"
os.environ["INTAKE_REQUIRE_PLAN_CONFIRM"] = "0"
os.environ["EMBED_FALLBACK_LEXICAL"] = "1"

sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _wait(client: TestClient, task_id: str) -> dict:
    for _ in range(80):
        t = client.get(f"/api/v1/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            return t
        time.sleep(0.15)
    raise AssertionError("task timeout")


def main() -> int:
    headers = {"X-Ops-Token": "smoke-ops"}
    sample = TMP / "e2e_inv.csv"
    sample.write_text(
        "物资编码,物资名称,现有数量,单位\nE1,冒烟螺丝,3,个\nE2,冒烟垫片,7,个\n",
        encoding="utf-8",
    )
    with TestClient(app) as client:
        with sample.open("rb") as f:
            up = client.post("/api/v1/files", files={"file": ("e2e_inv.csv", f, "text/csv")})
        assert up.status_code == 202, up.text
        fid = up.json()["file_id"]
        tid = up.json()["task_id"]
        done = _wait(client, tid)
        assert done["status"] == "done", done

        an = client.post(
            f"/api/v1/intake/analyze/{fid}",
            json={"target_domain": "inventory", "include_stage": True},
        )
        assert an.status_code == 200, an.text
        a = an.json()
        assert a.get("ok"), a
        print(
            "analyze",
            {
                "codes": a.get("codes"),
                "gate_ok": a.get("gate_ok"),
                "stage": (a.get("steps") or {}).get("stage", {}).get("status"),
                "map_enqueued": (a.get("steps") or {}).get("step2_map_queue", {}).get("enqueued"),
            },
        )

        # If gate blocked, force plan confirm then release with force
        force = not a.get("gate_ok")
        if force:
            pc = client.post(
                f"/api/v1/intake/plan/{fid}/confirm",
                headers=headers,
                json={"force": True, "note": "e2e force"},
            )
            assert pc.status_code == 200, pc.text

        conf = client.post(
            f"/api/v1/intake/stage/{fid}/confirm",
            headers=headers,
            json={"expected_status": "STAGED", "force": force},
        )
        assert conf.status_code == 200, conf.text
        rel = conf.json()["release"]["release_id"]
        rows = conf.json().get("rows")
        q = client.post(
            "/api/v1/query",
            headers=headers,
            json={"sql": f"SELECT COUNT(*) AS c FROM fact_inventory WHERE source_release_id='{rel}'"},
        )
        assert q.status_code == 200, q.text
        c = q.json()["data"][0]["c"]
        assert c == 2, (c, rows)

        # idempotent confirm
        conf2 = client.post(
            f"/api/v1/intake/stage/{fid}/confirm",
            headers=headers,
            json={"expected_status": "RELEASED"},
        )
        # may 409 if expected_status wrong — accept RELEASED idempotent path
        if conf2.status_code != 200:
            conf2 = client.post(f"/api/v1/intake/stage/{fid}/confirm", headers=headers)
        assert conf2.status_code == 200, conf2.text
        assert conf2.json().get("idempotent") is True or conf2.json()["release"]["release_id"] == rel

    print("INTAKE_E2E_OK")
    print(f"file_id={fid} release_id={rel} rows={c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
