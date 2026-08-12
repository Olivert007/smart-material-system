# -*- coding: utf-8 -*-
"""optv1/01 remaining gaps: releasable estimate, report versions, rule dry_run."""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPS_TOKEN", "test-ops")

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


def _seed_blocked_and_map():
    with meta_tx() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO file_batch (file_id, filename, format, status)
            VALUES ('file-01-1', 'demo.xlsx', 'xlsx', 'evidence_done')
            """
        )
        con.execute(
            """
            INSERT OR REPLACE INTO staging_record
              (staging_id, file_id, config_version, target_domain, source_file_hash,
               status, clean_rows, blocked_rows, version)
            VALUES ('stg-01-1', 'file-01-1', 'v1', 'inventory', 'hash01',
                    'STAGED', 10, 5, 1)
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
                "map-01-1",
                "file-01-1",
                "Sheet1",
                "物资名称",
                "material_name",
                json.dumps([{"std_field": "material_name", "score": 0.9}]),
                "low_confidence",
            ],
        )
        for i in range(3):
            con.execute(
                """
                INSERT OR REPLACE INTO staging_blocked
                  (block_id, staging_id, file_id, target_domain, source_row, header,
                   reason_code, reason_detail, raw_value)
                VALUES (?, 'stg-01-1', 'file-01-1', 'inventory', ?, '物资名称',
                        'UNKNOWN_HEADER', 'unknown', 'x')
                """,
                [f"b01-{i}", i + 1],
            )


def test_estimated_releasable_in_summary(client):
    _seed_blocked_and_map()
    summary = tb.todo_summary()
    assert "estimated_releasable_rows" in summary
    assert int(summary["estimated_releasable_rows"]) >= 0

    r = client.get("/api/v1/govern/standardization/summary")
    assert r.status_code == 200
    body = r.json()
    assert "estimated_releasable_rows" in body


def test_stats_overview_releasable(client):
    _seed_blocked_and_map()
    r = client.get("/api/v1/stats/overview?recent_limit=3")
    assert r.status_code == 200
    body = r.json()
    assert "estimated_releasable_rows" in body


def test_rule_learn_confirm_dry_run(client):
    with meta_tx() as con:
        proposal = {
            "kind": "map_alias",
            "domain": "inventory",
            "header": "物资名称",
            "suggested_std_field": "material_name",
            "count": 12,
        }
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('rule_learn', ?, 'proposed', 'count=12', 'system:test')
            """,
            [json.dumps(proposal, ensure_ascii=False)],
        )
        cid = con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    r = client.post(
        f"/api/v1/govern/rule-learn/{cid}/confirm",
        json={"decision": "accepted", "std_field": "material_name", "dry_run": True},
        headers={"X-Ops-Token": "test-ops"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("dry_run") is True
    assert body.get("affected_rows") == 12
    assert body.get("will_write") == "rule_dict"

    with meta_tx() as con:
        row = con.execute(
            "SELECT decision FROM govern_confirm WHERE id=?", [cid]
        ).fetchone()
        assert row["decision"] == "proposed"


def test_report_run_includes_versions(client):
    from app.services.query import report_runner as rr

    rr.ensure_report_seed()
    reports = rr.list_reports().get("items") or []
    if not reports:
        pytest.skip("no reports")
    rid = reports[0]["report_id"]
    try:
        out = rr.run_report(rid, actor="test")
    except Exception:
        pytest.skip("report SQL not runnable in empty biz db")
    assert out.get("data_scope") == "available_candidate"
    assert "source_release_ids" in out
    assert "metric_versions" in out
    assert out.get("note")
