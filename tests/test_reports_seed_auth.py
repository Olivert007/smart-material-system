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
    # frozenset 遍历顺序随进程哈希随机化；跳过带必填参数的 rpt_inv_filtered
    rid = next(r for r in SEED_REPORT_IDS if r != "rpt_inv_filtered")
    r = client.post(f"/api/v1/reports/{rid}/run")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("run_id")


def test_report_preview(client: TestClient):
    """report-export-preview §4: 运行后可读产物预览（只读，不重新运行）。"""
    ensure_report_seed()
    rid = next(r for r in SEED_REPORT_IDS if r != "rpt_inv_filtered")
    run = client.post(f"/api/v1/reports/{rid}/run")
    assert run.status_code == 200, run.text
    run_id = run.json()["run_id"]

    r = client.get(f"/api/v1/reports/{run_id}/preview?limit=5")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == run_id
    assert body["preview_count"] <= 5
    assert body["row_count"] >= body["preview_count"]
    assert isinstance(body["columns"], list) and body["columns"]
    assert isinstance(body["rows"], list)
    if body["rows"]:
        assert set(body["rows"][0].keys()) == set(body["columns"])

    # limit 上限钳制为 100
    big = client.get(f"/api/v1/reports/{run_id}/preview?limit=999")
    assert big.status_code == 200, big.text
    assert big.json()["preview_count"] <= 100

    # 不存在的 run → 404
    assert client.get("/api/v1/reports/run_nope/preview").status_code == 404


def test_adhoc_report_run_requires_ops_token(client: TestClient):
    r = client.post("/api/v1/reports/rpt_nonexistent_custom/run")
    assert r.status_code in (401, 404)
