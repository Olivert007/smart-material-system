# -*- coding: utf-8 -*-
"""Audit timeline filters: release_id / file_id / q (04 page gaps)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import meta_tx
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


def _seed_audits():
    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES (?, ?, ?, ?)
            """,
            [
                "release",
                "rel-audit-1",
                "ops",
                json.dumps({"file_id": "file-abc", "rows": 3}, ensure_ascii=False),
            ],
        )
        con.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES (?, ?, ?, ?)
            """,
            [
                "report_run",
                None,
                "ops",
                json.dumps({"report_id": "rpt_x", "run_id": "run_1"}, ensure_ascii=False),
            ],
        )
        con.execute(
            """
            INSERT INTO govern_confirm (source, decision, actor, detail, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            ["map", "accept", "govern", "header=物资名称 -> material_name", "规则沉淀"],
        )


def test_audit_timeline_filters(client):
    _seed_audits()
    all_r = client.get("/api/v1/audit/timeline?limit=50")
    assert all_r.status_code == 200
    assert all_r.json()["total"] >= 3

    by_rel = client.get("/api/v1/audit/timeline?release_id=rel-audit-1")
    assert by_rel.status_code == 200
    items = by_rel.json()["items"]
    assert items
    assert all(i.get("release_id") == "rel-audit-1" for i in items)
    assert any(i.get("file_id") == "file-abc" for i in items)

    by_file = client.get("/api/v1/audit/timeline?file_id=file-abc")
    assert by_file.status_code == 200
    assert by_file.json()["total"] >= 1

    by_q = client.get("/api/v1/audit/timeline?q=物资名称")
    assert by_q.status_code == 200
    assert by_q.json()["total"] >= 1
