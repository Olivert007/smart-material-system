# -*- coding: utf-8 -*-
"""JSON helpers and common API error shape."""
from __future__ import annotations

import math
import uuid
from typing import Any


def request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def json_safe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in records:
        cleaned: dict[str, Any] = {}
        for k, v in rec.items():
            if isinstance(v, float) and not math.isfinite(v):
                cleaned[k] = None
            elif v is None or isinstance(v, (str, int, float, bool)):
                cleaned[k] = v
            else:
                cleaned[k] = str(v)
        out.append(cleaned)
    return out


def error_body(*, error: str, message: str, code: str, details: dict | None = None, rid: str | None = None) -> dict:
    return {
        "error": error,
        "message": message,
        "code": code,
        "details": details or {},
        "request_id": rid or request_id(),
    }
