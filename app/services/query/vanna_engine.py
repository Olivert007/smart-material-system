# -*- coding: utf-8 -*-
"""Vanna NL2SQL engine with legacy fallback (docs/19 Step2)."""
from __future__ import annotations

import time

from app.services.query.ask_engine import AskEngineResult
from app.services.query.legacy_text2sql_engine import LegacyText2SqlEngine, extract_sql
from app.services.query.vanna_local import get_sms_vanna, vanna_available
from app.services.sql_guard import validate_readonly_sql


class VannaEngine:
    """Try Vanna once; on failure fall back to legacy text2sql."""

    def __init__(self) -> None:
        self._legacy = LegacyText2SqlEngine()

    def generate_sql(self, question: str, *, metric_match: dict | None = None) -> AskEngineResult:
        if not vanna_available():
            return self._fallback_legacy(question, metric_match, reason="vanna_unavailable")

        t0 = time.time()
        try:
            vn = get_sms_vanna()
            raw = vn.generate_sql(question, allow_llm_to_see_data=False)
            sql = extract_sql(raw or "")
            if not sql or str(raw or "").strip().lower().startswith("error"):
                raise ValueError(raw or "empty vanna sql")

            guard = validate_readonly_sql(sql)
            latency = int((time.time() - t0) * 1000)
            if not guard.ok:
                fb = self._fallback_legacy(
                    question,
                    metric_match,
                    reason="vanna_guard_failed",
                    vanna_sql=sql,
                    vanna_latency=latency,
                )
                fb.extra["vanna_guard_code"] = guard.code
                return fb

            return AskEngineResult(
                ok=True,
                sql=guard.sql,
                source="vanna",
                engine_state="sql_generated",
                model_state="vanna_sql_generated",
                model_request_attempted=True,
                model_invoked=True,
                output_available=True,
                latency_ms=latency,
            )
        except Exception as exc:
            return self._fallback_legacy(
                question,
                metric_match,
                reason="vanna_failed",
                vanna_error=str(exc),
            )

    def _fallback_legacy(
        self,
        question: str,
        metric_match: dict | None,
        *,
        reason: str,
        vanna_sql: str | None = None,
        vanna_latency: int = 0,
        vanna_error: str | None = None,
    ) -> AskEngineResult:
        res = self._legacy.generate_sql(question, metric_match=metric_match)
        res.engine_fallback = True
        res.fallback_reason = reason
        extra = dict(res.extra)
        if vanna_sql:
            extra["vanna_sql"] = vanna_sql
        if vanna_error:
            extra["vanna_error"] = vanna_error[:300]
        extra["vanna_attempt_ms"] = vanna_latency
        res.extra = extra
        return res
