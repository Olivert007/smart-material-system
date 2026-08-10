#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-2 smoke: staging_blocked details (STAGING_BLOCKED_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_blocked_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"
os.environ["WORKER_POLL_SEC"] = "0.15"
os.environ["EMBED_FALLBACK_LEXICAL"] = "1"
os.environ["INTAKE_REQUIRE_PLAN_CONFIRM"] = "0"

sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def _wait(client, tid):
    for _ in range(60):
        t = client.get(f"/api/v1/tasks/{tid}").json()
        if t["status"] in ("done", "failed"):
            return t
        time.sleep(0.15)
    raise AssertionError("timeout")


def main() -> int:
    csv = TMP / "bad.csv"
    csv.write_text(
        "物资编码,物资名称,现有数量,单位\n"
        "B1,好螺丝,3,个\n"
        "B2,, -1,个\n"  # blank name + negative qty → value_rule block
        "B3,垫片,-5,个\n",
        encoding="utf-8",
    )
    with TestClient(app) as client:
        with csv.open("rb") as f:
            up = client.post("/api/v1/files", files={"file": ("bad.csv", f, "text/csv")})
        assert up.status_code == 202, up.text
        fid = up.json()["file_id"]
        assert _wait(client, up.json()["task_id"])["status"] == "done"
        st = client.post(
            f"/api/v1/intake/stage/{fid}",
            json={"target_domain": "inventory"},
        )
        assert st.status_code == 200, st.text
        body = st.json()
        assert int(body.get("blocked_detail_count") or body.get("dry_run", {}).get("blocked_detail_count") or 0) >= 1

        q = client.get(f"/api/v1/stats/quality/{fid}")
        assert q.status_code == 200, q.text
        assert q.json()["detail_count"] >= 1

        bl = client.get(f"/api/v1/stats/quality/{fid}/blocked?limit=20")
        assert bl.status_code == 200, bl.text
        assert bl.json()["total"] >= 1
        codes = {i["reason_code"] for i in bl.json()["items"]}
        assert codes & {"VALUE_RANGE", "MISSING_COL", "TYPE_ERROR", "REQUIRED_UNMAPPED", "OTHER"}

    print("STAGING_BLOCKED_OK")
    print(f"file_id={fid} details={bl.json()['total']} codes={sorted(codes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
