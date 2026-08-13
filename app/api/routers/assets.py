# -*- coding: utf-8 -*-
"""Assets catalog endpoints under /api/v1 (A0-1 split from routes.py)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from app import config
from app.api.auth import require_ops
from app.api.routers._schemas import RuleDictStatusBody
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
    from app.services.govern.rule_dict import ensure_rule_dict_schema

    ensure_rule_dict_schema()
    con = meta_conn()
    try:
        total = con.execute("SELECT COUNT(*) AS c FROM rule_dict").fetchone()["c"]
        rows = con.execute(
            """
            SELECT r.rule_id, r.header, r.std_field, r.business_domain, r.hits,
                   r.source, r.confirmed_by, r.created_at, r.status, r.changed_by, r.updated_at,
                   (SELECT COUNT(*) FROM map_pending p
                     WHERE p.header = r.header AND p.status='pending') AS pending_map_hits,
                   (SELECT COUNT(*) FROM staging_blocked b
                     WHERE b.header = r.header) AS pending_blocked_hits
            FROM rule_dict
            AS r
            ORDER BY r.created_at DESC, r.rule_id DESC
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


@router.get("/assets/rule-dict/conflicts")
def assets_rule_dict_conflicts():
    """同一表头映射到多个标准字段的规则冲突视图。"""
    from app.services.govern.rule_dict import list_rule_conflicts

    return list_rule_conflicts()


@router.post("/assets/rule-dict/{rule_id}/preview")
def assets_rule_dict_preview(rule_id: int, body: RuleDictStatusBody | None = None):
    """规则启用/停用前的影响预演（不写任何状态）。"""
    from app.services.govern.rule_dict import set_rule_status

    action = body.action if body and body.action else "enable"
    try:
        return set_rule_status(
            rule_id=rule_id, action=action, actor="system:preview", dry_run=True
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "rule not found"})


@router.post("/assets/rule-dict/{rule_id}/confirm")
def assets_rule_dict_confirm(
    rule_id: int,
    body: RuleDictStatusBody,
    actor: str = Depends(require_ops),
):
    """确认启用/停用规则：先返回影响，再写状态与审计。"""
    from app.services.govern.rule_dict import set_rule_status

    try:
        return set_rule_status(
            rule_id=rule_id,
            action=body.action,
            actor=actor,
            note=body.note,
            idempotency_key=body.idempotency_key,
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "rule not found"})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_ACTION", "message": str(e)})
    except RuntimeError as e:
        msg = str(e)
        if msg.startswith("already_"):
            raise HTTPException(409, detail={"code": "STATUS_CONFLICT", "message": msg})
        raise HTTPException(400, detail={"code": "RULE_REFUSED", "message": msg})


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
