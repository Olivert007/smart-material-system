# -*- coding: utf-8 -*-
"""Audit timeline API (Wave 2)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app import config
from app.repositories import meta_conn

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.get("/audit/timeline")
def audit_timeline(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    source: str | None = None,
    actor: str | None = None,
):
    """Aggregate govern_confirm + write_audit into a single timeline."""
    con = meta_conn()
    try:
        gc_sql = """
            SELECT created_at AS ts, 'govern_confirm' AS kind, source, decision AS action,
                   actor, COALESCE(note, detail, '') AS detail
            FROM govern_confirm
        """
        wa_sql = """
            SELECT created_at AS ts, 'write_audit' AS kind, action AS source, action,
                   actor, COALESCE(detail_json, '') AS detail
            FROM write_audit
        """
        gc_params: list[object] = []
        wa_params: list[object] = []
        gc_where: list[str] = []
        wa_where: list[str] = []
        if source:
            gc_where.append("source = ?")
            gc_params.append(source)
            wa_where.append("action = ?")
            wa_params.append(source)
        if actor:
            gc_where.append("actor = ?")
            gc_params.append(actor)
            wa_where.append("actor = ?")
            wa_params.append(actor)
        if gc_where:
            gc_sql += " WHERE " + " AND ".join(gc_where)
        if wa_where:
            wa_sql += " WHERE " + " AND ".join(wa_where)
        gc_sql += " ORDER BY created_at DESC LIMIT ?"
        wa_sql += " ORDER BY created_at DESC LIMIT ?"
        fetch_n = limit + offset + 50
        gc_rows = con.execute(gc_sql, [*gc_params, fetch_n]).fetchall()
        wa_rows = con.execute(wa_sql, [*wa_params, fetch_n]).fetchall()
    finally:
        con.close()

    items = [dict(r) for r in gc_rows] + [dict(r) for r in wa_rows]
    items.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    page = items[offset : offset + limit]
    return {"total": len(items), "limit": limit, "offset": offset, "items": page}
