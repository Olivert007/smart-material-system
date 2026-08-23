# -*- coding: utf-8 -*-
"""Model runtime classification (doc 20 M4)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelRoleConfig:
    role: str
    port: int
    model_dir: str
    served_name: str


def role_configs_from_env(env: dict[str, str] | None = None) -> dict[str, ModelRoleConfig]:
    """Return fast/big/embed configs using unified env names."""
    e = env or {}
    return {
        "fast": ModelRoleConfig(
            role="fast",
            port=int(e.get("VLLM_FAST_PORT", "8000")),
            model_dir=e.get("MODEL_DIR_FAST", "/models/Qwen2.5-7B-Instruct"),
            served_name=e.get("VLLM_FAST_MODEL", e.get("LLM_FAST_MODEL", "qwen2.5-7b")),
        ),
        "big": ModelRoleConfig(
            role="big",
            port=int(e.get("VLLM_BIG_PORT", "8001")),
            model_dir=e.get("MODEL_DIR_BIG", "/models/Qwen3.6-27B-FP8"),
            served_name=e.get("VLLM_BIG_MODEL", e.get("LLM_BIG_MODEL", "qwen3.6-27b")),
        ),
        "embed": ModelRoleConfig(
            role="embed",
            port=int(e.get("VLLM_EMBED_PORT", "8002")),
            model_dir=e.get("MODEL_DIR_EMBED", "/models/Qwen3-Embedding-0.6B"),
            served_name=e.get("VLLM_EMBED_MODEL", e.get("LLM_EMBED_MODEL", "qwen3-embedding-0.6b")),
        ),
    }


def model_matches(configured_model: str, served_models: list[str] | None) -> bool:
    """True iff configured model appears exactly in served_models."""
    if not configured_model:
        return False
    return configured_model in (served_models or [])


def compute_model_runtime(models_status: dict[str, Any]) -> dict[str, Any]:
    """Compute model runtime flags from /models/status-like data."""
    big = models_status.get("big") or {}
    fast = models_status.get("fast") or {}
    embed = models_status.get("embed") or {}

    big_ok = bool(big.get("ok"))
    fast_ok = bool(fast.get("ok"))
    embed_ok = bool(embed.get("ok"))

    fast_match = model_matches(str(fast.get("configured_model") or ""), list(fast.get("models") or []))
    big_match = model_matches(str(big.get("configured_model") or ""), list(big.get("models") or []))
    embed_match = model_matches(str(embed.get("configured_model") or ""), list(embed.get("models") or []))
    model_match = fast_match and big_match and embed_match

    blocking: list[str] = []
    warnings: list[str] = []

    if not fast_ok and not big_ok and not embed_ok:
        # none = API 未 ready（docs/17 口径）；模型均未启动但 API 在线时归为 dev_ok，
        # 避免首页把「本地模型未启动」误报为「后端或 worker 未启动」
        model_runtime = "dev_ok"
        blocking.extend(["fast_unavailable", "big_unavailable", "embed_unavailable"])
    elif fast_ok and not big_ok and not embed_ok:
        model_runtime = "fast_only"
        blocking.extend(["big_unavailable", "embed_unavailable"])
    elif fast_ok and big_ok and embed_ok and model_match:
        model_runtime = "full"
    else:
        model_runtime = "degraded"
        if not big_ok:
            blocking.append("big_unavailable")
        if not embed_ok:
            blocking.append("embed_unavailable")
        if not fast_ok:
            blocking.append("fast_unavailable")
        if fast_ok and not fast_match:
            warnings.append("fast_model_mismatch")
        if big_ok and not big_match:
            warnings.append("big_model_mismatch")
        if embed_ok and not embed_match:
            warnings.append("embed_model_mismatch")

    if not embed_ok and embed.get("lexical_fallback"):
        warnings.append("embed_lexical_fallback")
    if model_runtime != "full":
        warnings.append("stage_degraded")

    stage_map = {"none": 0, "dev_ok": 0, "fast_only": 2, "degraded": 2, "full": 2}
    return {
        "model_runtime": model_runtime,
        "model_match": model_match,
        "blocking": blocking,
        "warnings": warnings,
        "stage": stage_map.get(model_runtime, 1),
    }
