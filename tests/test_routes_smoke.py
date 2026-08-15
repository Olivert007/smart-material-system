# -*- coding: utf-8 -*-
"""A1-2: routes.py TestClient smoke — broad endpoint coverage (safety net for A0-1 split).

Hits a sampling of GET endpoints across domains to assert they are registered
and respond with expected status codes. Does not exercise write paths (covered
by test_phase_a_accept). Point: catch router-level regressions early.

Uses the app lifespan (via TestClient context manager) so init_meta + seed
hooks run and the meta schema is bootstrapped. The intake worker is disabled
(worker.start patched to no-op) to avoid the pre-existing DuckDB mixed-mode
read/write race (A0-4) flapping these route-registration checks.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# 治理写接口（map-suggest/map-enqueue）已加 require_ops 鉴权（docs §9.8）
os.environ["OPS_TOKEN"] = "test-ops"

from app.main import app
from app.workers import intake_worker


@pytest.fixture(autouse=True)
def _disable_worker():
    # Avoid the DuckDB read/write race (A0-4) flapping route-registration smoke.
    orig = intake_worker.worker.start
    intake_worker.worker.start = lambda: None
    yield
    intake_worker.worker.start = orig


@pytest.fixture()
def client():
    # Function-scoped so lifespan (init_meta + seeds) runs AFTER the autouse
    # _isolated_data_dir fixture has repointed config paths to this test's tmp dir.
    with TestClient(app) as c:
        yield c


def test_health_live(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "live"


def test_health_ready(client):
    # Worker disabled → readiness should report worker=False → 503, or 200 if
    # the probe runs before the disabled start is observed. Accept either; the
    # point is the endpoint is registered and returns a structured body.
    r = client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    assert "biz_db" in body and "worker" in body


def test_api_root(client):
    r = client.get("/api")
    assert r.status_code == 200
    assert r.json()["api"] == "/api/v1"


def test_files_list(client):
    r = client.get("/api/v1/files")
    assert r.status_code == 200
    body = r.json()
    # Paginated envelope: {limit, offset, total, next_offset, ...}
    assert "total" in body and "limit" in body


def test_metrics_list(client):
    r = client.get("/api/v1/metrics")
    assert r.status_code == 200
    body = r.json()
    # Paginated envelope: {total, items: [...]}
    assert "total" in body and isinstance(body.get("items"), list)


def test_govern_map_pending(client):
    r = client.get("/api/v1/govern/map/pending")
    assert r.status_code == 200


def test_assets_rule_dict(client):
    r = client.get("/api/v1/assets/rule-dict")
    assert r.status_code == 200


def test_stats_overview(client):
    r = client.get("/api/v1/stats/overview")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_models_status(client):
    r = client.get("/api/v1/models/status")
    assert r.status_code == 200
    body = r.json()
    assert "big" in body and "embed" in body


def test_reports_list(client):
    r = client.get("/api/v1/reports")
    assert r.status_code == 200


def test_query_tables_list(client):
    r = client.get("/api/v1/query/tables")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_materials_standardized_filters(client):
    r = client.get("/api/v1/materials/standardized/filters")
    assert r.status_code == 200
    body = r.json()
    assert "categories" in body and "locations" in body


def test_map_suggest_requires_headers(client):
    # 未带操作令牌 -> 401（docs §9.8 鉴权验收）
    r = client.post("/api/v1/govern/map-suggest", json={"headers": ["物资编码"]})
    assert r.status_code == 401

    # 配置操作令牌 -> 200
    r = client.post(
        "/api/v1/govern/map-suggest",
        json={"headers": ["物资编码"]},
        headers={"X-Ops-Token": "test-ops"},
    )
    assert r.status_code == 200


def test_map_suggest_empty_headers_400(client):
    r = client.post(
        "/api/v1/govern/map-suggest",
        json={"headers": []},
        headers={"X-Ops-Token": "test-ops"},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "HEADERS_REQUIRED"
