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


@router.get("/analytics/flow-summary")
def analytics_flow_summary(categories: str | None = None, year: str | None = None):
    """数据成果页·趋势分析：流水概览 KPI（总条数/入库/出库/净变化/涉及物资/日期范围）。"""
    from app.services.analytics import flow_summary

    return flow_summary(categories=categories, year=year)


@router.get("/analytics/inventory-health")
def analytics_inventory_health(top_n: int = 10):
    """数据成果页·趋势分析：库存健康（类别/区域分布、低库存、超定额 TOP）。"""
    from app.services.analytics import inventory_health

    return inventory_health(top_n=top_n)


@router.get("/analytics/asset-overview")
def analytics_asset_overview(limit: int = 12):
    """数据成果页·趋势分析：资产清查（状态/公司/区域/购买年份分布、盘点问题 TOP）。"""
    from app.services.analytics import asset_overview

    return asset_overview(limit=limit)


@router.get("/analytics/demand-overview")
def analytics_demand_overview():
    """数据成果页·趋势分析：需求统计（按需求期间汇总）。"""
    from app.services.analytics import demand_overview

    return demand_overview()


@router.get("/analytics/quota-overview")
def analytics_quota_overview(limit: int = 10):
    """数据成果页·趋势分析：定额调整概览（调整类型分布 + 调整项 TOP）。"""
    from app.services.analytics import quota_overview

    return quota_overview(limit=limit)


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
