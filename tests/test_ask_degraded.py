# -*- coding: utf-8 -*-
"""模型离线时复杂问数返回结构化降级信息（optv1/05 Q12 修复）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm.model_client import LlmResult
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


@pytest.fixture()
def _model_down(monkeypatch):
    import app.services.query.text2sql as t2s

    def fake_chat(**kwargs):
        return LlmResult(
            ok=False,
            model_state="local_model_unavailable",
            error="no healthy endpoint",
            model_request_attempted=True,
        )

    monkeypatch.setattr(t2s, "chat", fake_chat)


def test_ask_degraded_when_model_down(client, _model_down):
    r = client.post("/api/v1/ask", json={"question": "按库位统计库存记录数，取前10"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["degraded"] is True
    assert body["model_state"] == "local_model_unavailable"
    assert body["hint"]
    assert body["suggested_examples"]
    assert "metric_template_ask" in (body["available_capabilities"] or [])
