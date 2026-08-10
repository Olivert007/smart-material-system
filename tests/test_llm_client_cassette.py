# -*- coding: utf-8 -*-
"""A1-2: LLM client cassette test — mock the vLLM HTTP call (no live model needed).

Verifies chat() parses a canned OpenAI-compatible response, writes an llm_call
audit row, and that the circuit breaker opens after repeated failures. This is
the contract test for the Stage 1 LLM layer (text2sql / embed / flow_llm all go
through model_client.chat).
"""
from __future__ import annotations

import pytest

from app.repositories import init_meta, meta_tx
from app.services.llm import model_client


@pytest.fixture(autouse=True)
def _reset_circuit():
    # Each test starts with a fresh circuit so failures don't leak across tests.
    model_client._circuits.clear()
    init_meta()
    yield
    model_client._circuits.clear()


def _canned_chat_completion(text: str) -> dict:
    return {
        "choices": [
            {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def test_chat_parses_response_and_audits(monkeypatch):
    calls = []

    def fake_http_json(method, url, payload=None, timeout=30):
        calls.append((method, url, payload))
        return _canned_chat_completion('{"sql": "SELECT 1"}')

    monkeypatch.setattr(model_client, "_http_json", fake_http_json)
    monkeypatch.setattr(model_client.config, "LLM_BIG_ENDPOINT", "http://fake:8001/v1")
    monkeypatch.setattr(model_client.config, "LLM_BIG_MODEL", "fake-model")

    result = model_client.chat(
        role="big",
        messages=[{"role": "user", "content": "translate: how many items?"}],
        task_type="text2sql",
    )

    assert result.ok is True
    assert result.text == '{"sql": "SELECT 1"}'
    assert result.model_invoked is True
    assert result.output_available is True
    assert result.model_state == "llm_analysis_available"
    # payload carried the Qwen3.6 thinking flag
    assert calls[0][2]["chat_template_kwargs"] == {"enable_thinking": False}

    # audit row written
    with meta_tx() as con:
        row = con.execute(
            "SELECT ok, task_type, model_state FROM llm_call WHERE call_id=?",
            [result.call_id],
        ).fetchone()
    assert row is not None
    assert row["ok"] == 1
    assert row["task_type"] == "text2sql"


def test_chat_thinking_tag_stripped(monkeypatch):
    # Qwen3.6 may leak a partial </think> tag; chat() must strip everything before it.
    def fake_http_json(method, url, payload=None, timeout=30):
        return _canned_chat_completion('reasoning\n</think>\n{"sql": "SELECT 2"}')

    monkeypatch.setattr(model_client, "_http_json", fake_http_json)
    monkeypatch.setattr(model_client.config, "LLM_BIG_ENDPOINT", "http://fake:8001/v1")
    monkeypatch.setattr(model_client.config, "LLM_BIG_MODEL", "fake-model")

    result = model_client.chat(
        role="big", messages=[{"role": "user", "content": "x"}], task_type="text2sql"
    )
    assert result.ok is True
    assert result.text == '{"sql": "SELECT 2"}'


def test_chat_circuit_opens_after_repeated_failures(monkeypatch):
    monkeypatch.setattr(model_client.config, "LLM_BIG_ENDPOINT", "http://fake:8001/v1")
    monkeypatch.setattr(model_client.config, "LLM_BIG_MODEL", "fake-model")
    monkeypatch.setattr(model_client.config, "LLM_CIRCUIT_FAILS", 2)
    monkeypatch.setattr(model_client.config, "LLM_MAX_RETRIES", 0)

    def boom(method, url, payload=None, timeout=30):
        raise ConnectionError("model down")

    monkeypatch.setattr(model_client, "_http_json", boom)

    first = model_client.chat(role="big", messages=[{"role": "user", "content": "x"}], task_type="text2sql")
    assert first.ok is False
    assert first.model_state == "local_model_unavailable"

    second = model_client.chat(role="big", messages=[{"role": "user", "content": "x"}], task_type="text2sql")
    assert second.ok is False
    # After 2 fails the circuit should be open → next call short-circuits without HTTP.
    third = model_client.chat(role="big", messages=[{"role": "user", "content": "x"}], task_type="text2sql")
    assert third.ok is False
    assert third.model_state == "circuit_open"
    assert third.fallback_reason == "circuit_open"


def test_parse_json_object_extracts_from_markdown_fence():
    assert model_client.parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert model_client.parse_json_object('noise {"b": 2} trailing') == {"b": 2}
    assert model_client.parse_json_object("not json") is None
    assert model_client.parse_json_object('[1,2]') is None  # array, not object
