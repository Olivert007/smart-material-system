# -*- coding: utf-8 -*-
"""Ops endpoints under /api/v1 (A0-1 split from routes.py)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from app import config
from app.api.auth import require_ops
from app.repositories import meta_conn
from app.services import backup as backup_svc
from app.services.llm.model_runtime import compute_model_runtime
from app.services.llm.model_client import probe_endpoint

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.get("/models/status")
async def models_status():
    big, fast, embed = await asyncio.gather(
        asyncio.to_thread(probe_endpoint, config.LLM_BIG_ENDPOINT),
        asyncio.to_thread(probe_endpoint, config.LLM_FAST_ENDPOINT),
        asyncio.to_thread(probe_endpoint, config.LLM_EMBED_ENDPOINT),
    )
    payload = {
        "big": {**big, "configured_model": config.LLM_BIG_MODEL},
        "fast": {
            **fast,
            "configured_model": config.LLM_FAST_MODEL,
            "note": "Stage 2+ (7B transition)",
        },
        "embed": {
            **embed,
            "configured_model": config.LLM_EMBED_MODEL,
            "lexical_fallback": config.EMBED_FALLBACK_LEXICAL,
        },
    }
    runtime = compute_model_runtime(payload)
    return {
        "stage": runtime["stage"],
        **runtime,
        **payload,
    }


@router.post("/models/{role}/activate")
def models_activate(role: str, actor: str = Depends(require_ops)):
    """Wave 4: record active role mapping (controlled; no arbitrary shell restart)."""
    if role not in ("big", "fast", "embed"):
        raise HTTPException(400, detail={"code": "BAD_ROLE", "message": "role must be big|fast|embed"})
    con = meta_conn()
    try:
        con.execute(
            """
            INSERT INTO write_audit (action, actor, detail_json)
            VALUES (?, ?, ?)
            """,
            [f"model_activate_{role}", actor, f'{{"role":"{role}","note":"ui request"}}'],
        )
        con.commit()
    finally:
        con.close()
    return {"ok": True, "role": role, "note": "已记录切换请求；端点映射需运维脚本生效"}


@router.post("/models/{role}/restart")
def models_restart(role: str, actor: str = Depends(require_ops)):
    if role not in ("big", "fast", "embed"):
        raise HTTPException(400, detail={"code": "BAD_ROLE", "message": "role must be big|fast|embed"})
    con = meta_conn()
    try:
        con.execute(
            "INSERT INTO write_audit (action, actor, detail_json) VALUES (?, ?, ?)",
            [f"model_restart_{role}", actor, f'{{"role":"{role}"}}'],
        )
        con.commit()
    finally:
        con.close()
    return {"ok": True, "role": role, "note": "已记录重启请求；受控重启需运维脚本"}


@router.get("/ops/tasks")
def ops_tasks_summary():
    """Task queue counts for Ops dashboard."""
    con = meta_conn()
    try:
        rows = con.execute(
            "SELECT status, COUNT(*) AS n FROM intake_task GROUP BY status"
        ).fetchall()
        by_status = {str(r["status"]): int(r["n"]) for r in rows}
    finally:
        con.close()
    return {
        "pending": by_status.get("pending", 0),
        "processing": by_status.get("processing", 0),
        "done": by_status.get("done", 0),
        "failed": by_status.get("failed", 0),
        "by_status": by_status,
    }


@router.get("/ops/alerts")
def ops_alerts():
    """Active alerts (Wave 2 simplified)."""
    alerts: list[dict] = []
    con = meta_conn()
    try:
        stuck = con.execute(
            """
            SELECT task_id, filename, status, message, heartbeat_at
            FROM intake_task
            WHERE status='processing'
              AND heartbeat_at IS NOT NULL
              AND datetime(heartbeat_at) < datetime('now', '-30 minutes')
            LIMIT 20
            """
        ).fetchall()
        for r in stuck:
            alerts.append({
                "level": "warning",
                "rule": "task_stuck",
                "message": f"任务卡住: {r['filename']} ({r['task_id']})",
                "ts": r["heartbeat_at"],
            })
        failed = con.execute(
            "SELECT COUNT(*) FROM intake_task WHERE status='failed'"
        ).fetchone()[0]
        if failed:
            alerts.append({
                "level": "danger",
                "rule": "task_failed",
                "message": f"失败任务 {failed} 个",
                "ts": datetime.utcnow().isoformat(),
            })
    finally:
        con.close()
    return {"active": alerts, "count": len(alerts)}


@router.get("/ops/llm-cost")
def ops_llm_cost(days: int = 7):
    """LLM call stats from llm_call table."""
    days = max(1, min(days, 30))
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    con = meta_conn()
    try:
        total = con.execute(
            "SELECT COUNT(*) FROM llm_call WHERE date(created_at) >= date(?)", [since]
        ).fetchone()[0]
        ok = con.execute(
            "SELECT COUNT(*) FROM llm_call WHERE ok=1 AND date(created_at) >= date(?)", [since]
        ).fetchone()[0]
        by_day = con.execute(
            """
            SELECT date(created_at) AS day, COUNT(*) AS calls,
                   SUM(CASE WHEN ok=1 THEN 1 ELSE 0 END) AS ok_calls
            FROM llm_call WHERE date(created_at) >= date(?)
            GROUP BY date(created_at) ORDER BY day
            """,
            [since],
        ).fetchall()
    finally:
        con.close()
    return {
        "days": days,
        "total_calls": int(total or 0),
        "ok_calls": int(ok or 0),
        "failed_calls": int((total or 0) - (ok or 0)),
        "by_day": [dict(r) for r in by_day],
    }


@router.post("/ops/backup")
def ops_backup(actor: str = Depends(require_ops)):
    return backup_svc.create_backup(tag="manual")


@router.get("/ops/backups")
def ops_backups(limit: int = 20):
    return backup_svc.list_backups(limit=limit)


@router.get("/ops/restore-drill")
def ops_restore_drill_get():
    return backup_svc.get_restore_drill()


@router.post("/ops/restore-drill")
def ops_restore_drill_post(
    note: str = "",
    result: str = "ok",
    backup_id: str | None = None,
    actor: str = Depends(require_ops),
):
    return backup_svc.record_restore_drill(
        actor=actor, note=note, result=result, backup_id=backup_id
    )