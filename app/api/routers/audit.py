# -*- coding: utf-8 -*-
"""Audit timeline API (Wave 2)."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Query

from app import config
from app.repositories import meta_conn

router = APIRouter(prefix=config.API_V1_PREFIX)

_FILE_ID_RE = re.compile(r"file[_-]?id[\"'\s:=]+([A-Za-z0-9_-]+)", re.I)


def _parse_file_id(detail: str | None) -> str | None:
    if not detail:
        return None
    text = str(detail)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            for key in ("file_id", "source_file", "filename"):
                val = obj.get(key)
                if val:
                    return str(val)
    except Exception:
        pass
    m = _FILE_ID_RE.search(text)
    if m:
        return m.group(1)
    return None


@router.get("/audit/timeline")
def audit_timeline(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    source: str | None = None,
    actor: str | None = None,
    release_id: str | None = None,
    file_id: str | None = None,
    q: str | None = None,
):
    """Aggregate govern_confirm + write_audit into a single timeline.

    Filters:
    - source / actor: exact match (existing)
    - release_id: write_audit.release_id column
    - file_id: LIKE on write_audit.detail_json / govern_confirm.detail
    - q: keyword LIKE on detail text (rule/material weak search)
    """
    con = meta_conn()
    try:
        gc_sql = """
            SELECT created_at AS ts, 'govern_confirm' AS kind, source, decision AS action,
                   actor, COALESCE(note, detail, '') AS detail, NULL AS release_id
            FROM govern_confirm
        """
        wa_sql = """
            SELECT created_at AS ts, 'write_audit' AS kind, action AS source, action,
                   actor, COALESCE(detail_json, '') AS detail, release_id
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
        if release_id:
            # govern_confirm has no release_id column; only write_audit matches
            wa_where.append("release_id = ?")
            wa_params.append(release_id)
            gc_where.append("1 = 0")
        if file_id:
            like = f"%{file_id}%"
            gc_where.append("(COALESCE(detail, '') LIKE ? OR COALESCE(note, '') LIKE ?)")
            gc_params.extend([like, like])
            wa_where.append("COALESCE(detail_json, '') LIKE ?")
            wa_params.append(like)
        if q:
            like_q = f"%{q}%"
            gc_where.append("(COALESCE(detail, '') LIKE ? OR COALESCE(note, '') LIKE ? OR COALESCE(source, '') LIKE ?)")
            gc_params.extend([like_q, like_q, like_q])
            wa_where.append("(COALESCE(detail_json, '') LIKE ? OR COALESCE(action, '') LIKE ?)")
            wa_params.extend([like_q, like_q])
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

    items = []
    for r in list(gc_rows) + list(wa_rows):
        d = dict(r)
        detail = d.get("detail")
        d["file_id"] = _parse_file_id(detail if isinstance(detail, str) else None)
        items.append(d)
    items.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    page = items[offset : offset + limit]
    return {"total": len(items), "limit": limit, "offset": offset, "items": page}
