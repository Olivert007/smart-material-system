# -*- coding: utf-8 -*-
"""Doc 20: models watchdog heal behavior."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import models_watchdog as wd  # noqa: E402
from app.services.llm.model_runtime import compute_model_runtime  # noqa: E402


def test_heal_uses_bash_not_python(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return R()

    monkeypatch.setattr(wd.subprocess, "run", fake_run)
    out = wd.heal("big")
    assert calls[0][0] == "bash"
    assert "models.sh" in calls[0][1]
    assert out["heal_rc"] == 0


def test_heal_timeout_big_greater_than_fast():
    assert wd.HEAL_TIMEOUT_SEC["big"] > wd.HEAL_TIMEOUT_SEC["fast"]


def test_heal_failure_records_rc(monkeypatch):
    def fake_run(cmd, **kwargs):
        class R:
            returncode = 1
            stdout = ""
            stderr = "boom"

        return R()

    monkeypatch.setattr(wd.subprocess, "run", fake_run)
    out = wd.heal("fast")
    assert out["heal_rc"] == 1
    assert "boom" in out["heal_stdout_tail"]


def test_degraded_stage_when_fast_only_big_down():
    status = {
        "big": {"ok": False, "configured_model": "qwen3.6-27b", "models": []},
        "fast": {"ok": True, "configured_model": "qwen2.5-7b", "models": ["qwen2.5-7b"]},
        "embed": {"ok": False, "configured_model": "qwen3-embedding-0.6b", "models": []},
    }
    rt = compute_model_runtime(status)
    assert rt["stage"] == 2
    assert rt["model_runtime"] == "fast_only"
