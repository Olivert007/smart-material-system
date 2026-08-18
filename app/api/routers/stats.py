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


@router.get("/analytics/flow-filters")
def analytics_flow_filters():
    """趋势分析筛选项：物资种类枚举 + 流水年份。"""
    from app.services.analytics import flow_filters

    return flow_filters()


@router.get("/analytics/flow-monthly")
def analytics_flow_monthly(categories: str | None = None, year: str | None = None):
    """UI-1/UI-2：出入库按月趋势（只读，可按物资种类、年份筛选）。"""
    from app.services.analytics import flow_monthly

    return flow_monthly(categories=categories, year=year)


@router.get("/analytics/flow-top")
def analytics_flow_top(
    limit: int = 10,
    categories: str | None = None,
    year: str | None = None,
):
    """UI-1：Top 物资流水（IN/OUT 柱状数据源，可按物资种类、年份筛选）。"""
    from app.services.analytics import flow_top

    return flow_top(limit=limit, categories=categories, year=year)


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
def stats_quality_blocked(
    file_id: str,
    limit: int = 50,
    offset: int = 0,
    target_domain: str | None = None,
):
    from app.services import quality as quality_svc

    try:
        return quality_svc.list_blocked(
            file_id, limit=limit, offset=offset, target_domain=target_domain
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "staging not found"})
