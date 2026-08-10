# -*- coding: utf-8 -*-
"""Assets catalog endpoints under /api/v1 (A0-1 split from routes.py)."""
from __future__ import annotations

import json

from fastapi import APIRouter

from app import config
from app.repositories import meta_conn

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.get("/assets/flow-examples")
def flow_examples(limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    con = meta_conn()
    try:
        total = con.execute("SELECT COUNT(*) AS c FROM flow_example").fetchone()["c"]
        rows = con.execute(
            """
            SELECT example_id, text_norm, flow_json, level, hits, confirmed_by, updated_at
            FROM flow_example
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [limit, offset],
        ).fetchall()
    finally:
        con.close()
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["flow"] = json.loads(d.pop("flow_json") or "[]")
        except Exception:
            d["flow"] = []
        items.append(d)
    return {"total": total, "items": items}


@router.get("/assets/flow-configs")
def assets_flow_configs():
    """Seeded flow_config catalog (docs/12 A3)."""
    from app.services.flow_config import list_flow_configs

    items = list_flow_configs()
    return {"total": len(items), "items": items}


@router.get("/assets/rule-dict")
def assets_rule_dict(limit: int = 100, offset: int = 0):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    con = meta_conn()
    try:
        total = con.execute("SELECT COUNT(*) AS c FROM rule_dict").fetchone()["c"]
        rows = con.execute(
            """
            SELECT rule_id, header, std_field, business_domain, hits, source, confirmed_by, created_at
            FROM rule_dict
            ORDER BY created_at DESC, rule_id DESC
            LIMIT ? OFFSET ?
            """,
            [limit, offset],
        ).fetchall()
    finally:
        con.close()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }


@router.get("/assets/history")
def assets_history(limit: int = 50, offset: int = 0, source: str | None = None):
    """Govern confirm timeline (docs/07 §3.5)."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    con = meta_conn()
    try:
        if source:
            total = con.execute(
                "SELECT COUNT(*) AS c FROM govern_confirm WHERE source=?", [source]
            ).fetchone()["c"]
            rows = con.execute(
                """
                SELECT id, source, detail, decision, note, actor, created_at
                FROM govern_confirm
                WHERE source=?
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [source, limit, offset],
            ).fetchall()
        else:
            total = con.execute("SELECT COUNT(*) AS c FROM govern_confirm").fetchone()["c"]
            rows = con.execute(
                """
                SELECT id, source, detail, decision, note, actor, created_at
                FROM govern_confirm
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [limit, offset],
            ).fetchall()
    finally:
        con.close()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }


@router.get("/assets/fewshot")
def assets_fewshot(limit: int = 50, offset: int = 0):
    """sql_fewshot pool — table optional until Stage eval expands."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    con = meta_conn()
    try:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sql_fewshot'"
        ).fetchone()
        if not exists:
            return {
                "total": 0,
                "limit": limit,
                "offset": offset,
                "items": [],
                "note": "sql_fewshot table not created yet",
            }
        total = con.execute("SELECT COUNT(*) AS c FROM sql_fewshot").fetchone()["c"]
        rows = con.execute(
            """
            SELECT fewshot_id, question_type, question, sql_gold, hits, updated_at
            FROM sql_fewshot
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [limit, offset],
        ).fetchall()
    finally:
        con.close()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }
