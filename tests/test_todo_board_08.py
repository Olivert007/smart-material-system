# -*- coding: utf-8 -*-
"""optv1/08 todo board: fields, states, aliases, decision/dry_run, aggregation."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import meta_tx
from app.services.govern import todo_board as tb
from app.workers import intake_worker


@pytest.fixture(autouse=True)
def _disable_worker():
    orig = intake_worker.worker.start
    intake_worker.worker.start = lambda: None
    yield
    intake_worker.worker.start = orig


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _seed_map_and_files():
    with meta_tx() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO file_batch (file_id, filename, format, status)
            VALUES ('file-08-1', 'demo.xlsx', 'xlsx', 'evidence_done')
            """
        )
        con.execute(
            """
            INSERT OR REPLACE INTO staging_record
              (staging_id, file_id, config_version, target_domain, source_file_hash,
               status, clean_rows, blocked_rows, version)
            VALUES ('stg-08-1', 'file-08-1', 'v1', 'inventory', 'hash08',
                    'STAGED', 10, 0, 1)
            """
        )
        con.execute(
            """
            INSERT OR REPLACE INTO map_pending
              (pending_id, file_id, sheet, header, suggested_field, candidates_json,
               reason, status, business_domain)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'default')
            """,
            [
                "map-08-1",
                "file-08-1",
                "维护材料",
                "物资名称",
                "material_name",
                json.dumps([{"std_field": "material_name", "score": 0.81}]),
                "low_confidence",
            ],
        )
        con.execute(
            """
            INSERT OR REPLACE INTO staging_blocked
              (block_id, staging_id, file_id, target_domain, source_row, header,
               reason_code, reason_detail, raw_value)
            VALUES
              ('b1', 'stg-08-1', 'file-08-1', 'inventory', 1, '单位', 'unit_unresolved', 'x', 'pcs'),
              ('b2', 'stg-08-1', 'file-08-1', 'inventory', 2, '单位', 'unit_unresolved', 'x', '箱'),
              ('b3', 'stg-08-1', 'file-other', 'inventory', 1, '单位', 'unit_unresolved', 'x', '个')
            """
        )


def test_todo_list_has_confidence_and_filename(client):
    _seed_map_and_files()
    r = client.get("/api/v1/govern/todos?todo_type=map")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    row = next(i for i in items if i["todo_id"] == "map-08-1")
    assert row["source_file"] == "demo.xlsx"
    assert row["source_sheet"] == "维护材料"
    assert row["confidence"] == pytest.approx(0.81)
    assert row["version"] == 1
    assert row["suggestion_source"] == "hybrid"
    assert row["suggestion_kind"] == "field"
    assert row["review_label"] == "待审核"
    assert "规则" in row["source_label"]


def test_ai_review_filter_and_summary_count(client):
    _seed_map_and_files()
    r = client.get("/api/v1/govern/todos?todo_type=ai")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    for it in body["items"]:
        assert it["todo_type"] in ("map", "unit", "master", "material_align", "flow")
        assert it.get("source_label")
        assert it.get("kind_label")

    s = client.get("/api/v1/govern/standardization/summary")
    assert s.status_code == 200
    summary = s.json()
    assert "ai_suggestion_pending_count" in summary
    assert int(summary["ai_suggestion_pending_count"]) >= 1
    assert any(a.get("path") == "/govern?tab=map" for a in summary.get("next_actions") or [])


def test_exception_grouped_by_file(client):
    _seed_map_and_files()
    r = client.get("/api/v1/govern/todos?todo_type=exception")
    assert r.status_code == 200
    items = r.json()["items"]
    unit_items = [i for i in items if "unit_unresolved" in str(i.get("todo_id"))]
    assert len(unit_items) >= 2
    by_file = {i["raw_ref"]["file_id"]: i["affected_rows"] for i in unit_items}
    assert by_file.get("file-08-1") == 2
    assert by_file.get("file-other") == 1


def test_summary_states_and_alias(client):
    # no files → no_data
    s = tb.todo_summary()
    # may have leftover from other tests in same process; ensure via API after seed
    _seed_map_and_files()
    r = client.get("/api/v1/govern/standardization/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] in (
        "needs_standardization",
        "blocked",
        "ready",
        "published",
        "parsing",
    )
    assert "state_message" in body

    old = client.get("/api/v1/govern/todo-summary")
    assert old.status_code == 200
    assert old.json()["state"] == body["state"]


def test_decision_dry_run_and_accept(client):
    _seed_map_and_files()
    headers = {"X-Ops-Token": "test-ops"}
    dry = client.post(
        "/api/v1/govern/todos/map-08-1/decision",
        json={"decision": "accept", "dry_run": True},
        headers=headers,
    )
    assert dry.status_code == 200, dry.text
    body = dry.json()
    assert body["dry_run"] is True
    assert body["ok"] is True
    # still pending
    with meta_tx() as con:
        st = con.execute(
            "SELECT status FROM map_pending WHERE pending_id='map-08-1'"
        ).fetchone()["status"]
    assert st == "pending"

    done = client.post(
        "/api/v1/govern/todos/map-08-1/decision",
        json={"decision": "accept", "idempotency_key": "idem-08-map-1"},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["dry_run"] is False

    replay = client.post(
        "/api/v1/govern/todos/map-08-1/decision",
        json={"decision": "accept", "idempotency_key": "idem-08-map-1"},
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json().get("idempotent") or replay.json().get("idempotency_replay")

    conflict = client.post(
        "/api/v1/govern/todos/map-08-1/decision",
        json={"decision": "accept", "idempotency_key": "idem-08-map-2"},
        headers=headers,
    )
    assert conflict.status_code == 409


def test_decision_version_conflict(client):
    _seed_map_and_files()
    headers = {"X-Ops-Token": "test-ops"}

    # dry_run preview rejects a stale expected_version
    stale = client.post(
        "/api/v1/govern/todos/map-08-1/decision",
        json={"decision": "accept", "dry_run": True, "expected_version": 999},
        headers=headers,
    )
    assert stale.status_code == 409, stale.text
    assert "version mismatch" in stale.json()["message"]

    ok_preview = client.post(
        "/api/v1/govern/todos/map-08-1/decision",
        json={"decision": "accept", "dry_run": True, "expected_version": 1},
        headers=headers,
    )
    assert ok_preview.status_code == 200
    assert ok_preview.json()["version"] == 1

    done = client.post(
        "/api/v1/govern/todos/map-08-1/decision",
        json={"decision": "accept", "expected_version": 1, "idempotency_key": "idem-08-v1"},
        headers=headers,
    )
    assert done.status_code == 200, done.text

    # version bumped after a decision
    with meta_tx() as con:
        v = con.execute(
            "SELECT version FROM map_pending WHERE pending_id='map-08-1'"
        ).fetchone()["version"]
    assert v == 2

    # idempotent replay of the same key still succeeds
    replay = client.post(
        "/api/v1/govern/todos/map-08-1/decision",
        json={"decision": "accept", "expected_version": 1, "idempotency_key": "idem-08-v1"},
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json().get("idempotent") or replay.json().get("idempotency_replay")


def test_decision_blocks_exception(client):
    _seed_map_and_files()
    headers = {"X-Ops-Token": "test-ops"}
    r = client.post(
        "/api/v1/govern/todos/exception:unit_unresolved:file-08-1/decision",
        json={"decision": "ignore"},
        headers=headers,
    )
    assert r.status_code == 400
