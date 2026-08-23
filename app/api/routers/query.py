# -*- coding: utf-8 -*-
"""Query & ask endpoints under /api/v1 (A0-1 split from routes.py)."""
from __future__ import annotations

from fastapi import APIRouter

from app import config
from app.services import query as query_svc
from app.services import text2sql as ask_svc
from app.services.query.ask_insights import recommend_questions

from app.api.routers._schemas import AskBody

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.get("/query/tables")
def tables():
    return query_svc.list_tables()


@router.get("/ask/recommendations")
def ask_recommendations(model_available: bool = True):
    """Data-aware recommended questions for ask assistant (docs/17 P0)."""
    return recommend_questions(model_available=model_available)


@router.post("/ask")
def ask(body: AskBody):
    return ask_svc.ask(body.question)
