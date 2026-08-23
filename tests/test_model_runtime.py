# -*- coding: utf-8 -*-
"""Doc 20: model runtime classification."""
from __future__ import annotations

from app.services.llm.model_runtime import compute_model_runtime, model_matches


def test_model_matches_exact():
    assert model_matches("qwen2.5-7b", ["qwen2.5-7b"]) is True


def test_model_matches_rejects_fuzzy():
    assert model_matches("qwen2.5-7b", ["qwen2.5-omni-3b-local"]) is False


def test_fast_only_runtime():
    status = {
        "big": {"ok": False, "configured_model": "qwen3.6-27b", "models": []},
        "fast": {"ok": True, "configured_model": "qwen2.5-7b", "models": ["qwen2.5-7b"]},
        "embed": {"ok": False, "configured_model": "qwen3-embedding-0.6b", "models": []},
    }
    rt = compute_model_runtime(status)
    assert rt["model_runtime"] == "fast_only"
    assert "big_unavailable" in rt["blocking"]
    assert "embed_unavailable" in rt["blocking"]


def test_full_runtime():
    status = {
        "big": {"ok": True, "configured_model": "qwen3.6-27b", "models": ["qwen3.6-27b"]},
        "fast": {"ok": True, "configured_model": "qwen2.5-7b", "models": ["qwen2.5-7b"]},
        "embed": {"ok": True, "configured_model": "qwen3-embedding-0.6b", "models": ["qwen3-embedding-0.6b"]},
    }
    rt = compute_model_runtime(status)
    assert rt["model_runtime"] == "full"
    assert rt["model_match"] is True
    assert rt["stage"] == 2


def test_embed_lexical_fallback_warning():
    status = {
        "big": {"ok": False, "configured_model": "qwen3.6-27b", "models": []},
        "fast": {"ok": True, "configured_model": "qwen2.5-7b", "models": ["qwen2.5-7b"]},
        "embed": {
            "ok": False,
            "configured_model": "qwen3-embedding-0.6b",
            "models": [],
            "lexical_fallback": True,
        },
    }
    rt = compute_model_runtime(status)
    assert "embed_lexical_fallback" in rt["warnings"]
