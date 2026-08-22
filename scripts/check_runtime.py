# -*- coding: utf-8 -*-
"""Runtime acceptance checks (doc 17 R1-R2).

Usage:
    PYTHONPATH=. python3 scripts/check_runtime.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def model_matches(configured_model: str, served_models: list[str] | None) -> bool:
    """True iff configured model appears exactly in served_models."""
    if not configured_model:
        return False
    return configured_model in (served_models or [])


def compute_runtime_level(
    api: dict[str, Any],
    frontend: dict[str, Any],
    models: dict[str, Any],
) -> tuple[str, list[str], list[str], dict[str, bool]]:
    """Return (runtime_level, blocking, warnings, flags)."""
    blocking: list[str] = []
    warnings: list[str] = []
    flags = {
        "big_unavailable": True,
        "embed_unavailable": True,
        "fast_model_mismatch": False,
        "model_match": False,
    }

    if not api.get("ready"):
        blocking.append("api_not_ready")
        return "none", blocking, warnings, flags

    big = models.get("big") or {}
    fast = models.get("fast") or {}
    embed = models.get("embed") or {}

    big_ok = bool(big.get("ok"))
    fast_ok = bool(fast.get("ok"))
    embed_ok = bool(embed.get("ok"))

    flags["big_unavailable"] = not big_ok
    flags["embed_unavailable"] = not embed_ok

    fast_match = model_matches(str(fast.get("configured_model") or ""), list(fast.get("models") or []))
    big_match = model_matches(str(big.get("configured_model") or ""), list(big.get("models") or []))
    embed_match = model_matches(str(embed.get("configured_model") or ""), list(embed.get("models") or []))
    flags["fast_model_mismatch"] = fast_ok and not fast_match
    flags["model_match"] = fast_match and big_match and embed_match

    if not big_ok:
        blocking.append("big_unavailable")
    if not embed_ok:
        blocking.append("embed_unavailable")
    if not fast_ok:
        blocking.append("fast_unavailable")
    if flags["fast_model_mismatch"]:
        warnings.append("fast_model_mismatch")
    if not embed_ok and embed.get("lexical_fallback"):
        warnings.append("embed_lexical_fallback")

    if big_ok and fast_ok and embed_ok and flags["model_match"]:
        return "full", [], warnings, flags

    warnings.append("stage_degraded")
    return "stage1_degraded", blocking, warnings, flags


def _fetch_json(url: str, timeout: float = 3.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _probe_url(url: str, timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def check_runtime(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    api_base = env.get("API_BASE", "http://127.0.0.1:8010").rstrip("/")
    vite_port = env.get("VITE_DEV_PORT", "5173")
    vite_url = env.get("VITE_DEV_URL", f"http://127.0.0.1:{vite_port}")
    dist_path = Path(env.get("FRONTEND_DIST", str(ROOT / "frontend" / "dist")))

    api: dict[str, Any] = {"ready": False, "live": False}
    try:
        live = _fetch_json(f"{api_base}/health/live")
        api["live"] = live.get("status") == "live"
        ready_resp = _fetch_json(f"{api_base}/health/ready")
        api["ready"] = ready_resp.get("status") == "ready"
        api["ready_body"] = ready_resp
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        api["error"] = "api_unreachable"

    frontend = {
        "dist_ok": dist_path.is_dir() and (dist_path / "index.html").is_file(),
        "dist_path": str(dist_path),
        "vite_ok": _probe_url(vite_url),
        "vite_url": vite_url,
    }

    models: dict[str, Any] = {}
    if api.get("ready"):
        try:
            models = _fetch_json(f"{api_base}/api/v1/models/status")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            models = {"error": "models_status_unreachable"}

    runtime_level, blocking, warnings, flags = compute_runtime_level(api, frontend, models)

    return {
        "runtime_level": runtime_level,
        "blocking": blocking,
        "warnings": warnings,
        "model_match": flags["model_match"],
        "big_unavailable": flags["big_unavailable"],
        "embed_unavailable": flags["embed_unavailable"],
        "fast_model_mismatch": flags["fast_model_mismatch"],
        "api": api,
        "frontend": frontend,
        "models": models,
    }


def main() -> int:
    try:
        out = check_runtime()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(
            json.dumps(
                {"runtime_level": "none", "blocking": ["check_failed"], "error": str(e)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
