# -*- coding: utf-8 -*-
"""AskEngine: pluggable NL2SQL generation (legacy | vanna)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app import config


@dataclass
class AskEngineResult:
    """Candidate SQL from an ask engine; execution stays in text2sql."""

    ok: bool
    sql: str | None = None
    source: str = "llm_text2sql"
    engine_state: str = "not_attempted"
    error: str | None = None
    confidence: float | None = None
    code: str | None = None
    model: str | None = None
    model_request_attempted: bool = False
    model_invoked: bool = False
    output_available: bool = False
    model_state: str = "not_attempted"
    fallback_reason: str | None = None
    latency_ms: int = 0
    engine_fallback: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class AskEngine(Protocol):
    def generate_sql(self, question: str, *, metric_match: dict | None = None) -> AskEngineResult:
        ...


def get_ask_engine() -> AskEngine:
    """Return configured ask engine."""
    from app.services.query.legacy_text2sql_engine import LegacyText2SqlEngine

    mode = (config.ASK_ENGINE or "legacy").strip().lower()
    if mode == "vanna":
        from app.services.query.vanna_engine import VannaEngine

        return VannaEngine()
    return LegacyText2SqlEngine()
