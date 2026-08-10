# -*- coding: utf-8 -*-
"""P0-4: heartbeat timeout recovery uses heartbeat_at (docs/03 §3.1)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_hb_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["TASK_HEARTBEAT_TIMEOUT_SEC"] = "60"
os.environ["TASK_MAX_ATTEMPTS"] = "3"
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_conn, meta_tx  # noqa: E402
from app.services.intake import (  # noqa: E402
    recover_orphan_tasks,
    task_is_stale,
    parse_heartbeat_at,
)


def _ins(task_id: str, *, hb: str | None, attempt: int = 1) -> None:
    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO file_batch (file_id, filename, format, sha256, stored_path, status)
            VALUES (?, 'f.csv', 'csv', ?, '/tmp/x', 'uploaded')
            """,
            [task_id, task_id],
        )
        con.execute(
            """
            INSERT INTO intake_task (
                task_id, file_id, filename, task_type, status, progress, message,
                attempt, heartbeat_at
            ) VALUES (?, ?, 'f.csv', 'parse_evidence', 'processing', 10, 'stuck', ?, ?)
            """,
            [task_id, task_id, attempt, hb],
        )


def test_stale_helper() -> None:
    now = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)
    assert task_is_stale(None, now=now, timeout_sec=60) is True
    fresh = (now - timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S")
    assert task_is_stale(fresh, now=now, timeout_sec=60) is False
    old = (now - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
    assert task_is_stale(old, now=now, timeout_sec=60) is True
    assert parse_heartbeat_at(fresh) is not None


def test_recover_only_stale() -> None:
    init_meta()
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(seconds=10)).strftime("%Y-%m-%d %H:%M:%S")
    stale = (now - timedelta(seconds=600)).strftime("%Y-%m-%d %H:%M:%S")
    _ins("t_fresh", hb=fresh, attempt=1)
    _ins("t_stale", hb=stale, attempt=1)
    _ins("t_null", hb=None, attempt=1)
    n = recover_orphan_tasks()
    assert n == 2, n
    con = meta_conn()
    try:
        rows = {
            r["task_id"]: r["status"]
            for r in con.execute(
                "SELECT task_id, status, message FROM intake_task"
            ).fetchall()
        }
    finally:
        con.close()
    assert rows["t_fresh"] == "processing"
    assert rows["t_stale"] == "pending"
    assert rows["t_null"] == "pending"


def test_max_attempts_fails() -> None:
    init_meta()
    with meta_tx() as con:
        con.execute("DELETE FROM intake_task")
        con.execute("DELETE FROM file_batch")
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(seconds=600)).strftime("%Y-%m-%d %H:%M:%S")
    _ins("t_max", hb=stale, attempt=3)
    n = recover_orphan_tasks()
    assert n == 1
    con = meta_conn()
    try:
        st = con.execute("SELECT status, message FROM intake_task WHERE task_id='t_max'").fetchone()
    finally:
        con.close()
    assert st["status"] == "failed"
    assert "exceeded attempts" in (st["message"] or "")


def main() -> None:
    test_stale_helper()
    print("OK stale_helper")
    test_recover_only_stale()
    print("OK recover_only_stale")
    test_max_attempts_fails()
    print("OK max_attempts_fails")
    print("P0_4_OK")


if __name__ == "__main__":
    main()
