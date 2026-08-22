# -*- coding: utf-8 -*-
"""Doc 17: runtime_level computation unit tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_runtime import compute_runtime_level, model_matches  # noqa: E402


def test_model_matches_exact():
    assert model_matches("qwen2.5-7b", ["qwen2.5-7b"]) is True
    assert model_matches("qwen2.5-7b", ["qwen2.5-omni-3b-local"]) is False


def test_big_embed_missing_is_stage1_degraded():
    api = {"ready": True}
    frontend = {"vite_ok": True, "dist_ok": True}
    models = {
        "big": {"ok": False, "configured_model": "qwen3.6-27b", "models": []},
        "fast": {"ok": True, "configured_model": "qwen2.5-7b", "models": ["qwen2.5-7b"]},
        "embed": {"ok": False, "configured_model": "qwen3-embedding-0.6b", "models": [], "lexical_fallback": True},
    }
    level, blocking, warnings, flags = compute_runtime_level(api, frontend, models)
    assert level == "stage1_degraded"
    assert "big_unavailable" in blocking
    assert "embed_unavailable" in blocking
    assert flags["big_unavailable"] is True
    assert flags["embed_unavailable"] is True


def test_api_down_is_none():
    api = {"ready": False}
    frontend = {"vite_ok": False, "dist_ok": False}
    models = {}
    level, blocking, _, _ = compute_runtime_level(api, frontend, models)
    assert level == "none"
    assert "api_not_ready" in blocking


def test_all_models_match_is_full():
    api = {"ready": True}
    frontend = {"vite_ok": True, "dist_ok": True}
    models = {
        "big": {"ok": True, "configured_model": "qwen3.6-27b", "models": ["qwen3.6-27b"]},
        "fast": {"ok": True, "configured_model": "qwen2.5-7b", "models": ["qwen2.5-7b"]},
        "embed": {"ok": True, "configured_model": "qwen3-embedding-0.6b", "models": ["qwen3-embedding-0.6b"]},
    }
    level, blocking, _, flags = compute_runtime_level(api, frontend, models)
    assert level == "full"
    assert not blocking
    assert flags["model_match"] is True
