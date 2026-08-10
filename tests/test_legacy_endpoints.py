# -*- coding: utf-8 -*-
"""A2-1: legacy /query and /ingest endpoints — 404 when disabled, gated when enabled."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_legacy_query_404_when_disabled(monkeypatch):
    # Default deployment: ALLOW_FREE_QUERY=0 → /query returns 404 (A2-1).
    from app import config
    monkeypatch.setattr(config, "ALLOW_FREE_QUERY", False)
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/v1/query", json={"sql": "SELECT 1"}, headers={"X-Ops-Token": "test-ops"})
    assert r.status_code == 404, r.text


def test_legacy_ingest_404_when_disabled(monkeypatch):
    # Default deployment: ALLOW_LEGACY_INGEST=0 → /ingest returns 404 (A2-1).
    from app import config
    monkeypatch.setattr(config, "ALLOW_LEGACY_INGEST", False)
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/v1/ingest", headers={"X-Ops-Token": "test-ops"})
    assert r.status_code == 404, r.text


def test_legacy_ingest_501_when_enabled(monkeypatch):
    # When enabled, /ingest is registered but not ported in Phase A → 501 (A2-1).
    from app import config
    monkeypatch.setattr(config, "ALLOW_LEGACY_INGEST", True)
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/v1/ingest", headers={"X-Ops-Token": "test-ops"})
    assert r.status_code == 501, r.text
    assert r.json()["code"] == "NOT_IMPLEMENTED"


def test_legacy_query_requires_ops_token(monkeypatch):
    # /query requires ops token even when ALLOW_FREE_QUERY is on (C8).
    from app import config
    monkeypatch.setattr(config, "ALLOW_FREE_QUERY", True)
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/v1/query", json={"sql": "SELECT 1"})
    assert r.status_code == 401, r.text
