# -*- coding: utf-8 -*-
"""Deterministic PolicyRouter (docs/09) — no LLM-as-router."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app import config
from app.services.model_client import LlmResult, chat, probe_endpoint

Validator = Callable[[LlmResult], tuple[bool, list[str]]]


TASK_POLICIES: dict[str, dict[str, Any]] = {
    # Module 12 Phase B: flow pending suggest — low risk, no cross-check
    "flow_parse_suggest": {
        "primary": "fast",
        "escalate": "big",
        "risk": "low",
        "max_calls": 2,
        "temperature": 0.0,
        "max_tokens": 768,
    },
    "map_headers": {
        "primary": "fast",
        "escalate": "big",
        "risk": "medium",
        "max_calls": 2,
        "temperature": 0.0,
        "max_tokens": 1024,
    },
    "sql_simple": {
        "primary": "fast",
        "escalate": "big",
        "risk": "medium",
        "max_calls": 2,
        "temperature": 0.0,
        "max_tokens": 1024,
    },
}


@dataclass
class RouteResult:
    ok: bool
    result: LlmResult
    role_used: str
    mode: str  # direct | escalate | degraded_up | degraded_down | unavailable
    attempts: list[dict[str, Any]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def _role_available(role: str) -> bool:
    if role == "big":
        ep = config.LLM_BIG_ENDPOINT
    elif role == "fast":
        ep = config.LLM_FAST_ENDPOINT
    else:
        return False
    # cheap circuit check first via chat's circuit; probe for reachability
    probe = probe_endpoint(ep, timeout=2)
    return bool(probe.get("ok"))


def route_chat(
    *,
    task_type: str,
    messages: list[dict[str, str]],
    validate: Validator | None = None,
    force_role: str | None = None,
) -> RouteResult:
    """primary → validate → escalate; Stage1 may degraded_up fast→big when fast down."""
    policy = TASK_POLICIES.get(task_type) or {
        "primary": "big",
        "escalate": None,
        "max_calls": 1,
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    primary = force_role or policy.get("primary") or "big"
    escalate = None if force_role else policy.get("escalate")
    max_calls = int(policy.get("max_calls") or 1)
    temperature = float(policy.get("temperature") or 0.0)
    max_tokens = int(policy.get("max_tokens") or 1024)

    attempts: list[dict[str, Any]] = []
    mode = "direct"
    role = primary

    if not _role_available(role):
        if escalate and _role_available(escalate):
            role = escalate
            mode = "degraded_up"
        elif role != "big" and _role_available("big"):
            role = "big"
            mode = "degraded_up"
        elif role != "fast" and _role_available("fast"):
            role = "fast"
            mode = "degraded_down"
        else:
            empty = LlmResult(
                ok=False,
                model_state="local_model_unavailable",
                error="no healthy primary/escalate endpoint",
            )
            return RouteResult(
                ok=False, result=empty, role_used=primary, mode="unavailable", issues=["no_endpoint"]
            )

    calls = 0
    result = chat(
        role=role,
        messages=messages,
        task_type=task_type,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    calls += 1
    attempts.append({"role": role, "ok": result.ok, "state": result.model_state, "error": result.error})

    issues: list[str] = []
    valid = result.ok and result.output_available
    if validate and valid:
        valid, issues = validate(result)
    elif not valid:
        issues = [result.error or result.model_state or "llm_failed"]

    if (
        (not valid)
        and escalate
        and role != escalate
        and calls < max_calls
        and _role_available(escalate)
    ):
        mode = "escalate" if mode == "direct" else mode
        # hand fast failure context to big for full rewrite
        esc_messages = list(messages) + [
            {
                "role": "user",
                "content": (
                    "先前模型输出未通过校验，请输出完整修正版 JSON（非增量补丁）。"
                    f"问题: {', '.join(issues) or 'invalid'}; "
                    f"先前输出: {(result.text or '')[:800]}"
                ),
            }
        ]
        result2 = chat(
            role=escalate,
            messages=esc_messages,
            task_type=task_type,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        attempts.append(
            {"role": escalate, "ok": result2.ok, "state": result2.model_state, "error": result2.error}
        )
        result = result2
        role = escalate
        valid = result.ok and result.output_available
        if validate and valid:
            valid, issues = validate(result)
        elif not valid:
            issues = [result.error or result.model_state or "llm_failed"]

    return RouteResult(
        ok=bool(valid),
        result=result,
        role_used=role,
        mode=mode,
        attempts=attempts,
        issues=issues,
    )
