# -*- coding: utf-8 -*-
"""手动新建规则候选：只进待确认，不直接生效。"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["OPS_TOKEN"] = "test-ops"

from app.main import app
from app.workers import intake_worker

OPS = {"X-Ops-Token": "test-ops"}


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


def test_create_rule_candidate_stays_proposed(client):
    r = client.post(
        "/api/v1/govern/rule-learn/candidates",
        json={
            "rule_type": "field_alias",
            "header": "物料描述",
            "std_field": "material_name",
            "scope_note": "制度要求统一物资名称",
        },
        headers=OPS,
    )
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["ok"] is True
    assert body["decision"] == "proposed"
    listed = client.get("/api/v1/govern/rule-learn/candidates").json()
    assert any(it["id"] == body["id"] and it["decision"] == "proposed" for it in listed["items"])
    assert all(it["decision"] == "proposed" for it in listed["items"])
