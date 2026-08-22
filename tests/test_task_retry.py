# -*- coding: utf-8 -*-
"""Doc 16 E3/E4: retry failed parse_evidence tasks."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["OPS_TOKEN"] = "test-ops"

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories import init_meta, meta_tx  # noqa: E402
from app.services.intake.error_info import encode_error_message, map_exception_to_error  # noqa: E402
from app.workers import intake_worker  # noqa: E402

TASK_ID = "t-retry-1"
FILE_ID = "f-retry-1"


@pytest.fixture(autouse=True)
def _disable_worker():
    orig = intake_worker.worker.start
    intake_worker.worker.start = lambda: None
    yield
    intake_worker.worker.start = orig


def _seed_failed_task(*, retryable: bool = True) -> None:
    init_meta()
    info = map_exception_to_error(
        Exception("Conversion failed for column asset_qty"),
        phase="write_evidence",
    )
    if not retryable:
        info = map_exception_to_error(Exception("unsupported format: .doc"), phase="load_evidence")
    msg = encode_error_message(info)
    with meta_tx() as con:
        con.execute(
            "INSERT OR REPLACE INTO file_batch (file_id, filename, format, status) "
            "VALUES (?, ?, ?, ?)",
            [FILE_ID, "sample.xlsx", "xlsx", "failed"],
        )
        con.execute(
            """
            INSERT OR REPLACE INTO intake_task
            (task_id, file_id, filename, task_type, status, progress, message, attempt)
            VALUES (?, ?, ?, 'parse_evidence', 'failed', 0, ?, 1)
            """,
            [TASK_ID, FILE_ID, "sample.xlsx", msg],
        )


def test_retry_task_requeues_and_cleans_evidence(tmp_path):
    config.RAW.mkdir(parents=True, exist_ok=True)
    cell = config.RAW / f"{FILE_ID}.parquet"
    tab = config.RAW / f"{FILE_ID}.tabular.parquet"
    cell.write_bytes(b"partial")
    tab.write_bytes(b"partial")
    _seed_failed_task(retryable=True)

    with TestClient(app) as client:
        r = client.post(
            f"/api/v1/tasks/{TASK_ID}/retry",
            headers={"X-Ops-Token": "test-ops"},
        )
    assert r.status_code == 202
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "pending"
    assert body["task_id"] == TASK_ID
    assert body["file_id"] == FILE_ID
    assert not cell.exists()
    assert not tab.exists()

    with meta_tx() as con:
        task = con.execute("SELECT status FROM intake_task WHERE task_id=?", [TASK_ID]).fetchone()
        fb = con.execute("SELECT status FROM file_batch WHERE file_id=?", [FILE_ID]).fetchone()
    assert task["status"] == "pending"
    assert fb["status"] == "uploaded"


def test_retry_not_retryable_returns_409():
    _seed_failed_task(retryable=False)
    with TestClient(app) as client:
        r = client.post(
            f"/api/v1/tasks/{TASK_ID}/retry",
            headers={"X-Ops-Token": "test-ops"},
        )
    assert r.status_code == 409
    assert r.json()["code"] == "TASK_NOT_RETRYABLE"


def test_retry_non_failed_returns_409():
    _seed_failed_task()
    with meta_tx() as con:
        con.execute("UPDATE intake_task SET status='done' WHERE task_id=?", [TASK_ID])
    with TestClient(app) as client:
        r = client.post(
            f"/api/v1/tasks/{TASK_ID}/retry",
            headers={"X-Ops-Token": "test-ops"},
        )
    assert r.status_code == 409
    assert r.json()["code"] == "TASK_NOT_FAILED"


def test_get_task_flattens_error_fields():
    _seed_failed_task()
    with TestClient(app) as client:
        r = client.get(f"/api/v1/tasks/{TASK_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["error_code"] == "TABULAR_PARQUET_TYPE_ERROR"
    assert body["phase"] == "write_evidence"
    assert body["retryable"] is True
    assert body["user_message"]
    assert body["next_actions"]
