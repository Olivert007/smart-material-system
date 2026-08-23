# -*- coding: utf-8 -*-
"""Doc 20 M1: models.sh is the sole lifecycle entry."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LEGACY_START_SCRIPTS = (
    "start_vllm_big.sh",
    "start_fast_7b.sh",
    "start_vllm_embed.sh",
    "start_vllm_big27.sh",
)


def test_legacy_start_scripts_delegate_to_models_sh():
    for name in LEGACY_START_SCRIPTS:
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "models.sh" in text
        assert "DEPRECATED" in text


def test_models_sh_has_wait_and_stop_helpers():
    text = (ROOT / "scripts" / "models.sh").read_text(encoding="utf-8")
    assert "wait_ready()" in text
    assert "role_pid_file" in text
    assert "FORCE_KILL" in text
    assert "VLLM_FAST_MODEL" in text
    assert "ALLOW_DEGRADED_START" in text
