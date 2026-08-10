# -*- coding: utf-8 -*-
"""Intake upload enqueue + task recovery (docs/03 §3.1)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.repositories import meta_tx
from app.services.evidence import load_to_evidence, save_evidence, sha256_file


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def short_id(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def parse_heartbeat_at(value: str | None) -> datetime | None:
    """Parse meta heartbeat timestamps (UTC, naive stored as UTC wall clock)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1]
    if "+" in s[10:]:
        s = s.split("+", 1)[0]
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def task_is_stale(
    heartbeat_at: str | None,
    *,
    now: datetime | None = None,
    timeout_sec: int | None = None,
) -> bool:
    """True when heartbeat missing/unparseable or older than TASK_HEARTBEAT_TIMEOUT_SEC."""
    timeout = config.TASK_HEARTBEAT_TIMEOUT_SEC if timeout_sec is None else int(timeout_sec)
    ts = parse_heartbeat_at(heartbeat_at)
    if ts is None:
        return True
    age = ((now or _now_dt()) - ts).total_seconds()
    return age > timeout


def touch_heartbeat(task_id: str, *, message: str | None = None) -> None:
    with meta_tx() as con:
        if message is None:
            con.execute(
                "UPDATE intake_task SET heartbeat_at=? WHERE task_id=? AND status='processing'",
                [_now(), task_id],
            )
        else:
            con.execute(
                """
                UPDATE intake_task
                SET heartbeat_at=?, message=?
                WHERE task_id=? AND status='processing'
                """,
                [_now(), message[:200], task_id],
            )


def recover_orphan_tasks() -> int:
    """Requeue processing tasks whose heartbeat is missing or past timeout (docs/03 §3.1)."""
    cutoff_sec = config.TASK_HEARTBEAT_TIMEOUT_SEC
    now = _now_dt()
    with meta_tx() as con:
        rows = con.execute(
            "SELECT task_id, heartbeat_at, attempt FROM intake_task WHERE status='processing'"
        ).fetchall()
        n = 0
        for r in rows:
            if not task_is_stale(r["heartbeat_at"], now=now, timeout_sec=cutoff_sec):
                continue
            attempt = int(r["attempt"] or 0)
            if attempt >= config.TASK_MAX_ATTEMPTS:
                con.execute(
                    """
                    UPDATE intake_task
                    SET status='failed', message=?, finished_at=?, heartbeat_at=NULL
                    WHERE task_id=?
                    """,
                    [
                        f"exceeded attempts after heartbeat timeout ({cutoff_sec}s)",
                        _now(),
                        r["task_id"],
                    ],
                )
            else:
                con.execute(
                    """
                    UPDATE intake_task
                    SET status='pending', message=?, heartbeat_at=NULL
                    WHERE task_id=?
                    """,
                    [f"requeued: heartbeat stale (>{cutoff_sec}s)", r["task_id"]],
                )
            n += 1
        return n


def enqueue_upload(*, filename: str, stored_path: Path, file_id: str | None = None) -> dict:
    fid = file_id or short_id()
    task_id = short_id()
    digest = sha256_file(stored_path)
    ext = stored_path.suffix.lstrip(".").lower()
    with meta_tx() as con:
        # Same hash: reuse existing file_id if already evidence_done
        existing = con.execute(
            "SELECT file_id, status FROM file_batch WHERE sha256=? ORDER BY created_at DESC LIMIT 1",
            [digest],
        ).fetchone()
        if existing and existing["status"] in ("evidence_done", "staged", "released"):
            return {
                "file_id": existing["file_id"],
                "task_id": None,
                "status": existing["status"],
                "reused": True,
                "sha256": digest,
            }
        con.execute(
            """
            INSERT INTO file_batch (file_id, filename, format, sha256, stored_path, status)
            VALUES (?, ?, ?, ?, ?, 'uploaded')
            """,
            [fid, filename, ext, digest, str(stored_path)],
        )
        con.execute(
            """
            INSERT INTO intake_task (task_id, file_id, filename, task_type, status, progress, message, attempt)
            VALUES (?, ?, ?, 'parse_evidence', 'pending', 0, 'queued', 0)
            """,
            [task_id, fid, filename],
        )
    return {
        "file_id": fid,
        "task_id": task_id,
        "status": "pending",
        "status_url": f"{config.API_V1_PREFIX}/tasks/{task_id}",
        "reused": False,
        "sha256": digest,
    }


def process_parse_evidence(task_id: str) -> None:
    with meta_tx() as con:
        task = con.execute("SELECT * FROM intake_task WHERE task_id=?", [task_id]).fetchone()
        if not task:
            return
        file_id = task["file_id"]
        fb = con.execute("SELECT * FROM file_batch WHERE file_id=?", [file_id]).fetchone()
        if not fb:
            con.execute(
                "UPDATE intake_task SET status='failed', message=?, finished_at=? WHERE task_id=?",
                ["file_batch missing", _now(), task_id],
            )
            return
        con.execute(
            """
            UPDATE intake_task
            SET status='processing', progress=5, heartbeat_at=?, attempt=attempt+1, message='parsing'
            WHERE task_id=?
            """,
            [_now(), task_id],
        )
        path = Path(fb["stored_path"])

    try:
        touch_heartbeat(task_id, message="loading evidence")
        df, fmt, n_sheets, tabular = load_to_evidence(path, file_id)
        touch_heartbeat(task_id, message="writing evidence")
        save_evidence(df, file_id, tabular=tabular)
        # Step1 rule workbook profile (docs/03 §1.2) — no LLM
        touch_heartbeat(task_id, message="profiling workbook")
        from app.services.profile import profile_from_evidence, save_workbook_profile

        profile_payload = profile_from_evidence(df)
        report_id = save_workbook_profile(file_id, profile_payload)
        n_need = len(profile_payload.get("workbook", {}).get("needs_llm_sheets") or [])
        # Step2: enqueue uncertain headers (meta only; never writes DuckDB)
        map_enqueued = 0
        try:
            touch_heartbeat(task_id, message="enqueue map pending")
            from app.services.map_gov import enqueue_from_file

            mq = enqueue_from_file(file_id)
            map_enqueued = int(mq.get("enqueued") or 0)
        except Exception:
            # Profile success must not fail on map queue; surface via message only
            map_enqueued = -1
        with meta_tx() as con:
            con.execute(
                """
                UPDATE file_batch
                SET format=?, rows=?, sheets=?, status='evidence_done'
                WHERE file_id=?
                """,
                [fmt, int(len(df)), int(n_sheets), file_id],
            )
            con.execute(
                """
                UPDATE intake_task
                SET status='done', progress=100,
                    message=?,
                    finished_at=?, heartbeat_at=?
                WHERE task_id=?
                """,
                [
                    (
                        f"evidence+profile ready (report={report_id}; needs_llm={n_need}; "
                        f"map_pending={map_enqueued})"
                    ),
                    _now(),
                    _now(),
                    task_id,
                ],
            )
    except Exception as e:
        with meta_tx() as con:
            con.execute(
                """
                UPDATE intake_task
                SET status='failed', message=?, finished_at=?, heartbeat_at=?
                WHERE task_id=?
                """,
                [str(e)[:500], _now(), _now(), task_id],
            )
            con.execute(
                "UPDATE file_batch SET status='failed' WHERE file_id=?",
                [file_id],
            )


def claim_next_task() -> str | None:
    with meta_tx() as con:
        row = con.execute(
            """
            SELECT task_id FROM intake_task
            WHERE status='pending'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        tid = row["task_id"]
        cur = con.execute(
            """
            UPDATE intake_task
            SET status='processing', heartbeat_at=?, message='claimed'
            WHERE task_id=? AND status='pending'
            """,
            [_now(), tid],
        )
        if cur.rowcount != 1:
            return None
        return tid
