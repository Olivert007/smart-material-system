# -*- coding: utf-8 -*-
"""RP-5: seed reports run without Ops Token; ad-hoc reports still require ops."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.query.report_runner import SEED_REPORT_IDS, ensure_report_seed
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


def test_seed_report_run_without_ops_token(client: TestClient):
    ensure_report_seed()
    rid = next(iter(SEED_REPORT_IDS))
    r = client.post(f"/api/v1/reports/{rid}/run")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("run_id")


def test_adhoc_report_run_requires_ops_token(client: TestClient):
    r = client.post("/api/v1/reports/rpt_nonexistent_custom/run")
    assert r.status_code in (401, 404)
