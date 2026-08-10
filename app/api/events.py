# -*- coding: utf-8 -*-
"""SSE event streams (docs/11 §7) — task status SSOT remains SQLite."""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.repositories import meta_conn

router = APIRouter(tags=["events"])


def _task_snapshot(task_id: str) -> dict | None:
    con = meta_conn()
    try:
        row = con.execute("SELECT * FROM intake_task WHERE task_id=?", [task_id]).fetchone()
        if not row:
            return None
        d = dict(row)
        return {
            "task_id": d.get("task_id"),
            "file_id": d.get("file_id"),
            "filename": d.get("filename"),
            "status": d.get("status"),
            "progress": int(d.get("progress") or 0),
            "message": d.get("message"),
            "attempt": d.get("attempt"),
            "finished_at": d.get("finished_at"),
        }
    finally:
        con.close()


@router.get("/events/tasks/{task_id}")
async def events_task(task_id: str):
    """Server-Sent Events for intake task progress. Reconnect: GET /api/v1/tasks/{id}."""
    snap = _task_snapshot(task_id)
    if not snap:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "task not found"})

    async def gen():
        last_key = None
        # heartbeat keep-alive for proxies
        idle = 0.0
        while True:
            cur = _task_snapshot(task_id)
            if not cur:
                yield f"event: error\ndata: {json.dumps({'code': 'NOT_FOUND'})}\n\n"
                break
            key = (cur["status"], cur["progress"], cur.get("message"), cur.get("finished_at"))
            if key != last_key:
                yield f"event: task\ndata: {json.dumps(cur, ensure_ascii=False)}\n\n"
                last_key = key
                idle = 0.0
            else:
                idle += 0.5
                if idle >= 15.0:
                    yield f": ping {int(time.time())}\n\n"
                    idle = 0.0
            if cur["status"] in ("done", "failed"):
                yield f"event: end\ndata: {json.dumps(cur, ensure_ascii=False)}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
