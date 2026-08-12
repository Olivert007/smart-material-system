# -*- coding: utf-8 -*-
"""optv1/04 数据接入：上传完成后的业务结论（可规整/需字段/需结构/无法接入）。"""
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


def _seed_file(file_id: str, status: str):
    with meta_tx() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO file_batch (file_id, filename, format, status)
            VALUES (?, 'demo.xlsx', 'xlsx', ?)
            """,
            [file_id, status],
        )


def _seed_analyze(file_id: str, codes: list[str]):
    with meta_tx() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO intake_report (report_id, file_id, report_type, payload_json)
            VALUES (?, ?, 'intake_analyze', ?)
            """,
            [f"ar-{file_id}", file_id, json.dumps({"codes": codes}, ensure_ascii=False)],
        )


def test_failed_file_conclusion(client):
    _seed_file("file-conc-fail", "failed")
    r = client.get("/api/v1/intake/conclusion/file-conc-fail")
    assert r.status_code == 200
    body = r.json()
    assert body["conclusion"] == "failed"
    assert "无法接入" in body["hint"]


def test_field_work_conclusion(client):
    _seed_file("file-conc-field", "evidence_done")
    _seed_analyze("file-conc-field", ["QUALITY_BLOCKING", "MISSING_REQUIRED"])
    r = client.get("/api/v1/intake/conclusion/file-conc-field")
    assert r.status_code == 200
    body = r.json()
    assert body["conclusion"] == "field_work"
    assert "需字段处理" in body["hint"]
    assert "MISSING_REQUIRED" in body["reason_codes"]


def test_structure_work_conclusion(client):
    _seed_file("file-conc-struct", "evidence_done")
    _seed_analyze("file-conc-struct", ["PROFILE_FAILED", "NO_COLUMNS"])
    r = client.get("/api/v1/intake/conclusion/file-conc-struct")
    assert r.status_code == 200
    body = r.json()
    assert body["conclusion"] == "structure_work"
    assert "需结构确认" in body["hint"]


def test_staging_ready_conclusion(client):
    _seed_file("file-conc-ready", "evidence_done")
    _seed_analyze("file-conc-ready", [])
    r = client.get("/api/v1/intake/conclusion/file-conc-ready")
    assert r.status_code == 200
    body = r.json()
    assert body["conclusion"] == "staging_ready"
    assert "可进入规整" in body["hint"]


def test_published_and_parsing_conclusions(client):
    _seed_file("file-conc-pub", "released")
    r = client.get("/api/v1/intake/conclusion/file-conc-pub")
    assert r.json()["conclusion"] == "published"

    _seed_file("file-conc-parsing", "processing")
    r = client.get("/api/v1/intake/conclusion/file-conc-parsing")
    assert r.json()["conclusion"] == "parsing"


def test_conclusion_missing_file_404(client):
    r = client.get("/api/v1/intake/conclusion/no-such-file")
    assert r.status_code == 404
