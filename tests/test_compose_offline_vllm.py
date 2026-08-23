# -*- coding: utf-8 -*-
"""Doc 21: compose-offline requires pinned VLLM_IMAGE."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compose_offline_uses_vllm_image_env():
    text = (ROOT / "deploy" / "compose-offline.yml").read_text(encoding="utf-8")
    assert "VLLM_IMAGE" in text
    assert "vllm-openai:latest" not in text
