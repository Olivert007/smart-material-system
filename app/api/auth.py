# -*- coding: utf-8 -*-
"""Ops auth helpers (docs/05 §1.5)."""
from __future__ import annotations

from fastapi import Header, HTTPException

from app import config

VALID_ROLES = frozenset({"viewer", "intake", "govern", "ops"})


def _resolve_role(x_ops_role: str | None) -> str:
    role = (x_ops_role or "ops").strip().lower()
    if role not in VALID_ROLES:
        return "ops"
    return role


def require_ops_or_seed_report(
    report_id: str,
    x_ops_token: str | None = Header(default=None, alias="X-Ops-Token"),
) -> str:
    """Seed reports (read-only SQL) may run without Ops Token; ad-hoc reports require ops."""
    from app.services.query.report_runner import SEED_REPORT_IDS

    if report_id in SEED_REPORT_IDS:
        if x_ops_token and x_ops_token == config.OPS_TOKEN:
            return "ops"
        return "viewer"
    if not x_ops_token or x_ops_token != config.OPS_TOKEN:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "code": "OPS_AUTH_REQUIRED"})
    return "ops"


def require_ops(x_ops_token: str | None = Header(default=None, alias="X-Ops-Token")) -> str:
    if not x_ops_token or x_ops_token != config.OPS_TOKEN:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "code": "OPS_AUTH_REQUIRED"})
    return "ops"


def require_role(
    *allowed: str,
):
    """Dependency factory: token valid + role in allowed (ops always passes)."""

    def _dep(
        x_ops_token: str | None = Header(default=None, alias="X-Ops-Token"),
        x_ops_role: str | None = Header(default=None, alias="X-Ops-Role"),
    ) -> str:
        if not x_ops_token or x_ops_token != config.OPS_TOKEN:
            raise HTTPException(status_code=401, detail={"error": "unauthorized", "code": "OPS_AUTH_REQUIRED"})
        role = _resolve_role(x_ops_role)
        if role == "ops" or role in allowed:
            return role
        raise HTTPException(status_code=403, detail={"error": "forbidden", "code": "ROLE_FORBIDDEN"})

    return _dep


def actor_from_ops(token_ok: str) -> str:
    return token_ok
