#!/usr/bin/env python3
"""F3 smoke: upload returns events_url; SSE streams task → done."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "sandboxes" / "test_f3_sse"
if TEST_DATA.exists():
    shutil.rmtree(TEST_DATA)
os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["WORKER_POLL_SEC"] = "0.2"
os.environ["FLOW_LLM_ENABLED"] = "0"

from app.main import app  # noqa: E402
from app.services.intake import claim_next_task, process_parse_evidence  # noqa: E402


def main() -> None:
    with TestClient(app) as client:
        p = TEST_DATA / "a.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("物资名称,数量\n光纤,1\n", encoding="utf-8")
        with p.open("rb") as f:
            r = client.post("/api/v1/files", files={"file": ("a.csv", f, "text/csv")})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body.get("events_url"), body
        assert body.get("status_url"), body
        task_id = body["task_id"]
        events_url = body["events_url"]
        assert events_url == f"/events/tasks/{task_id}"

        # Drive worker so SSE can observe progress
        claimed = claim_next_task()
        assert claimed == task_id
        # Consume SSE in a thread while processing
        events: list[dict] = []

        def _consume():
            with client.stream("GET", events_url) as resp:
                assert resp.status_code == 200
                buf = ""
                for chunk in resp.iter_text():
                    buf += chunk
                    while "\n\n" in buf:
                        block, buf = buf.split("\n\n", 1)
                        if "event: task" in block or "event: end" in block:
                            for line in block.splitlines():
                                if line.startswith("data: "):
                                    import json

                                    events.append(json.loads(line[6:]))
                        if any(e.get("status") in ("done", "failed") for e in events):
                            return

        import threading

        th = threading.Thread(target=_consume, daemon=True)
        th.start()
        time.sleep(0.2)
        process_parse_evidence(task_id)
        th.join(timeout=15)
        assert events, "no SSE events"
        assert any(e.get("status") == "done" for e in events), events
        print("events", [(e.get("status"), e.get("progress")) for e in events])
        print("F3_SSE_OK")


if __name__ == "__main__":
    main()
