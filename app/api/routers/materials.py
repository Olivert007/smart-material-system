# -*- coding: utf-8 -*-
"""已规整物资台账浏览 / 筛选 / 导出（optv3/material-standization-filtering.md）。"""
from __future__ import annotations

from fastapi import APIRouter

from app import config
from app.services.query import materials_standardized as svc

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.get("/materials/standardized/filters")
def standardized_filters():
    """物资种类固定枚举 + 台账中已出现的存放区域（不可手输不存在的区域）。"""
    return svc.list_filters()


@router.get("/materials/standardized")
def list_standardized(
    categories: str | None = None,
    locations: str | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
    sort_by: str | None = None,
    sort_order: str | None = None,
):
    """已规整物资台账分页浏览。只读；筛选参数化绑定。"""
    return svc.list_standardized(
        categories=categories,
        locations=locations,
        q=q,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/materials/standardized/export")
def export_standardized(
    categories: str | None = None,
    locations: str | None = None,
    q: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
):
    """按当前筛选条件导出 CSV（白名单字段 + 公式注入防护）。0 条拒绝导出。"""
    return svc.export_standardized(
        categories=categories,
        locations=locations,
        q=q,
        sort_by=sort_by,
        sort_order=sort_order,
    )
