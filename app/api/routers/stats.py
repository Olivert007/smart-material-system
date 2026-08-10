# -*- coding: utf-8 -*-
"""Stats & analytics endpoints under /api/v1 (A0-1 split from routes.py)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import config
from app.services import stats_overview as stats_overview_svc

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.get("/stats/overview")
def stats_overview(recent_limit: int = 5):
    """Dashboard overview cards (docs/07 §3.1)."""
    return stats_overview_svc.overview(recent_limit=recent_limit)


@router.get("/analytics/flow-monthly")
def analytics_flow_monthly():
    """UI-1/UI-2：出入库按月趋势（只读，与 ReportsView rpt_flow_monthly 同口径）。"""
    from app.services.analytics import flow_monthly

    return flow_monthly()


@router.get("/analytics/flow-top")
def analytics_flow_top(limit: int = 10):
    """UI-1：Top 物资流水（IN/OUT 柱状数据源）。"""
    from app.services.analytics import flow_top

    return flow_top(limit=limit)


@router.get("/analytics/flow-level")
def analytics_flow_level():
    """UI-1：L1/L2/L3 占比（与 /govern/flow/stats 同源）。"""
    from app.services.analytics import flow_level_ratio

    return flow_level_ratio()


@router.get("/stats/quality/release/{release_id}")
def stats_quality_release(release_id: str):
    from app.services import quality as quality_svc

    try:
        return quality_svc.quality_report_by_release(release_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "release not found"})


@router.get("/stats/quality/{file_id}")
def stats_quality(file_id: str):
    from app.services import quality as quality_svc

    try:
        return quality_svc.quality_report(file_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "staging not found"})


@router.get("/stats/quality/{file_id}/blocked")
def stats_quality_blocked(file_id: str, limit: int = 50, offset: int = 0):
    from app.services import quality as quality_svc

    try:
        return quality_svc.list_blocked(file_id, limit=limit, offset=offset)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "staging not found"})
