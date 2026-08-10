# -*- coding: utf-8 -*-
"""Idempotency-Key cache for side-effect APIs (docs/11 §6.4)."""
from __future__ import annotations

import json
from typing import Any

from app.repositories import meta_conn, meta_tx


def get(scope: str, key: str) -> dict[str, Any] | None:
    con = meta_conn()
    try:
        row = con.execute(
            "SELECT response_json FROM idempotency_record WHERE idem_key=? AND scope=?",
            [key, scope],
        ).fetchone()
    finally:
        con.close()
    if not row:
        return None
    try:
        data = json.loads(row["response_json"])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def put(scope: str, key: str, response: dict[str, Any], request_id: str | None = None) -> None:
    payload = json.dumps(response, ensure_ascii=False, default=str)
    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO idempotency_record (idem_key, scope, response_json, request_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(idem_key) DO NOTHING
            """,
            [key, scope, payload, request_id],
        )
