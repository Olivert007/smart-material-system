# -*- coding: utf-8 -*-
"""Legacy endpoints (A2-1): free SQL query + legacy ingest.

Always mounted so the OpenAPI surface stays stable across env configs (C14),
but each handler returns 404 when its gate flag is off — a default deployment
does not expose the legacy surface. See docs/question/07 §3.3 A2-1.

- POST /query   — free-form readonly SQL (requires ops token + ALLOW_FREE_QUERY)
- POST /ingest  — legacy write port (ALLOW_LEGACY_INGEST; not implemented in Phase A)

When /ingest is eventually ported, it MUST validate any SQL via sql_guard with a
write whitelist (INSERT/UPDATE only on allowlisted tables), matching the AST
defense C12 applied to /query. Until then it returns 501 when enabled.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.api.auth import require_ops
from app.services import query as query_svc


class QueryBody(BaseModel):
    sql: str = Field(..., min_length=1)


router = APIRouter(prefix=config.API_V1_PREFIX)


@router.post("/query")
def legacy_query(body: QueryBody, actor: str = Depends(require_ops)):
    if not config.ALLOW_FREE_QUERY:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "not found"})
    return query_svc.run_readonly_query(body.sql, allow_free=True, row_limit=config.QUERY_ROW_LIMIT)


@router.post("/ingest")
def legacy_ingest(actor: str = Depends(require_ops)):
    if not config.ALLOW_LEGACY_INGEST:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "not found"})
    raise HTTPException(
        501,
        detail={"code": "NOT_IMPLEMENTED", "message": "legacy ingest not ported in Phase A"},
    )
