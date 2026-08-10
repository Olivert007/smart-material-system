# -*- coding: utf-8 -*-
"""Phase A API routes under /api/v1 — aggregation entry.

A0-1: the original monolith app/api/routes.py (85 endpoints) was split by
domain into app/api/routers/*. Each sub-router keeps
prefix=config.API_V1_PREFIX; this router carries no prefix of its own and
simply includes them in the original endpoint order so route registration
order / matching priority stays unchanged (main.py keeps importing `router`).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import assets, audit, files, govern, intake, metrics, ops, query, reports, stats

router = APIRouter()

router.include_router(files.router)
router.include_router(intake.router)
router.include_router(query.router)
router.include_router(govern.router)
router.include_router(metrics.router)
router.include_router(assets.router)
router.include_router(stats.router)
router.include_router(reports.router)
router.include_router(ops.router)
router.include_router(audit.router)
