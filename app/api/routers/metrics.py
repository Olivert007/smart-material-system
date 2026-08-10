# -*- coding: utf-8 -*-
"""Metrics endpoints under /api/v1 (A0-1 split from routes.py).

Registration order matters: /metrics/flow/activate (static) must stay before
/metrics/{metric_id} (param) exactly as in the original routes.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import config
from app.api.auth import require_ops
from app.services import metrics as metrics_svc

from app.api.routers._schemas import AskBody, FlowActivateBody, MetricUpsertBody

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.get("/metrics/fixtures")
def metrics_fixtures():
    """08 fixed fixtures (isolated sandbox)."""
    from app.services.metric_fixtures import run_metric_fixtures

    return run_metric_fixtures()


@router.post("/metrics/flow/activate")
def metrics_flow_activate(body: FlowActivateBody, actor: str = Depends(require_ops)):
    """D4 — activate FLOW_* when gate ready."""
    try:
        return metrics_svc.activate_flow_metrics(actor=actor, metric_ids=body.metric_ids)
    except PermissionError as e:
        raise HTTPException(403, detail={"code": "FLOW_GATE", "message": str(e)})


@router.get("/metrics")
def metrics_list(status: str | None = None):
    return metrics_svc.list_metrics(status=status)


@router.post("/metrics/match")
def metrics_match(body: AskBody):
    """Rule: question → metric candidates (docs/08 §8)."""
    return metrics_svc.match_metrics(body.question)


@router.post("/metrics/check")
def metrics_check():
    """docs/08: overlapping alias/name conflicts across metrics."""
    return metrics_svc.check_metric_conflicts()


@router.get("/metrics/{metric_id}/snapshots")
def metrics_snapshots(metric_id: str, limit: int = 20):
    return metrics_svc.list_metric_snapshots(metric_id, limit=limit)


@router.get("/metrics/{metric_id}")
def metrics_get(metric_id: str):
    try:
        return metrics_svc.get_metric(metric_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "metric not found"})


@router.post("/metrics/{metric_id}/evaluate")
def metrics_evaluate(metric_id: str):
    try:
        return metrics_svc.evaluate_metric(metric_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "metric not found"})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_SQL", "message": str(e)})


@router.post("/metrics")
def metrics_upsert(body: MetricUpsertBody, actor: str = Depends(require_ops)):
    try:
        return metrics_svc.upsert_metric(
            metric_id=body.metric_id,
            metric_name=body.metric_name,
            definition_sql=body.definition_sql,
            actor=actor,
            aliases=body.aliases,
            unit=body.unit,
            definition=body.definition,
            source_tables=body.source_tables,
            engine=body.engine,
            status=body.status,
        )
    except PermissionError as e:
        raise HTTPException(403, detail={"code": "FLOW_GATE", "message": str(e)})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_METRIC", "message": str(e)})
