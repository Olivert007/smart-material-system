# -*- coding: utf-8 -*-
"""File upload & task endpoints under /api/v1 (A0-1 split from routes.py)."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app import config
from app.api.auth import require_ops
from app.repositories import meta_conn
from app.services import intake as intake_svc

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.post("/files", status_code=202)
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, detail={"code": "FILENAME_REQUIRED", "message": "filename required"})
    # path traversal / absolute
    name = os.path.basename(file.filename)
    if not name or name != file.filename.replace("\\", "/").split("/")[-1]:
        raise HTTPException(400, detail={"code": "BAD_FILENAME", "message": "invalid filename"})

    from app.services.upload_limits import assert_dir_quota, parse_limit_error

    try:
        assert_dir_quota(incoming_bytes=0)  # refuse when already over quota
    except ValueError as e:
        code, msg = parse_limit_error(e)
        raise HTTPException(400, detail={"code": code, "message": msg})

    fid = intake_svc.short_id()
    ext = Path(name).suffix.lstrip(".").lower() or "bin"
    config.UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
    config.UPLOAD.mkdir(parents=True, exist_ok=True)
    tmp = config.UPLOAD_TMP / f"{fid}.{ext}.part"
    final = config.UPLOAD / f"{fid}.{ext}"
    size = 0
    try:
        with tmp.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > config.UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        400,
                        detail={"code": "UPLOAD_TOO_LARGE", "message": f"max {config.UPLOAD_MAX_BYTES} bytes"},
                    )
                out.write(chunk)
        # tmp already under uploads/ — usage includes it; don't double-count
        try:
            assert_dir_quota(incoming_bytes=0)
        except ValueError as e:
            code, msg = parse_limit_error(e)
            raise HTTPException(400, detail={"code": code, "message": msg})
        tmp.replace(final)
    except HTTPException:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    except Exception as e:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise HTTPException(400, detail={"code": "UPLOAD_FAILED", "message": str(e)})

    result = intake_svc.enqueue_upload(filename=name, stored_path=final, file_id=fid)
    if result.get("reused"):
        # remove duplicate bytes
        if final.exists() and result["file_id"] != fid:
            final.unlink(missing_ok=True)
        return {
            **result,
            "filename": name,
            "status_url": None,
            "events_url": None,
        }
    task_id = result.get("task_id")
    return {
        **result,
        "filename": name,
        "bytes": size,
        "status_url": f"/api/v1/tasks/{task_id}" if task_id else None,
        "events_url": f"/events/tasks/{task_id}" if task_id else None,
    }


@router.post("/files/batch", status_code=202)
async def upload_files_batch(files: list[UploadFile] = File(...)):
    """Multi-file upload with UPLOAD_MAX_FILES / BATCH_BYTES / DIR_QUOTA (05 §1.4)."""
    from app.services.upload_limits import assert_batch_limits, assert_dir_quota, parse_limit_error

    if not files:
        raise HTTPException(400, detail={"code": "UPLOAD_EMPTY_BATCH", "message": "no files"})
    try:
        assert_batch_limits(file_count=len(files), batch_bytes=0)
    except ValueError as e:
        code, msg = parse_limit_error(e)
        raise HTTPException(400, detail={"code": code, "message": msg})

    config.UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
    config.UPLOAD.mkdir(parents=True, exist_ok=True)

    # Stream all to temp first; enforce per-file + running batch + quota
    staged: list[tuple[str, Path, Path, int]] = []  # name, tmp, final, size
    batch_bytes = 0
    try:
        for file in files:
            if not file.filename:
                raise HTTPException(400, detail={"code": "FILENAME_REQUIRED", "message": "filename required"})
            name = os.path.basename(file.filename)
            if not name or name != file.filename.replace("\\", "/").split("/")[-1]:
                raise HTTPException(400, detail={"code": "BAD_FILENAME", "message": "invalid filename"})
            fid = intake_svc.short_id()
            ext = Path(name).suffix.lstrip(".").lower() or "bin"
            tmp = config.UPLOAD_TMP / f"{fid}.{ext}.part"
            final = config.UPLOAD / f"{fid}.{ext}"
            size = 0
            with tmp.open("wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > config.UPLOAD_MAX_BYTES:
                        raise HTTPException(
                            400,
                            detail={
                                "code": "UPLOAD_TOO_LARGE",
                                "message": f"{name}: max {config.UPLOAD_MAX_BYTES} bytes",
                            },
                        )
                    out.write(chunk)
            batch_bytes += size
            try:
                assert_batch_limits(file_count=len(files), batch_bytes=batch_bytes)
                # staged parts already under uploads/tmp
                assert_dir_quota(incoming_bytes=0)
            except ValueError as e:
                code, msg = parse_limit_error(e)
                raise HTTPException(400, detail={"code": code, "message": msg})
            staged.append((name, tmp, final, size))

        items = []
        for name, tmp, final, size in staged:
            tmp.replace(final)
            fid = final.stem  # fid.ext → but stem may include dots; use name from path
            # final is uploads/{fid}.{ext}
            file_id = final.name.rsplit(".", 1)[0]
            result = intake_svc.enqueue_upload(filename=name, stored_path=final, file_id=file_id)
            if result.get("reused") and final.exists() and result["file_id"] != file_id:
                final.unlink(missing_ok=True)
            task_id = result.get("task_id")
            items.append(
                {
                    **result,
                    "filename": name,
                    "bytes": size,
                    "status_url": f"/api/v1/tasks/{task_id}" if task_id else None,
                    "events_url": f"/events/tasks/{task_id}" if task_id else None,
                }
            )
        return {
            "ok": True,
            "count": len(items),
            "batch_bytes": batch_bytes,
            "items": items,
        }
    except HTTPException:
        for _n, tmp, _f, _s in staged:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        raise
    except Exception as e:
        for _n, tmp, _f, _s in staged:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        raise HTTPException(400, detail={"code": "UPLOAD_FAILED", "message": str(e)})


@router.get("/files")
def list_files(limit: int = 20, offset: int = 0):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    con = meta_conn()
    try:
        total = con.execute("SELECT COUNT(*) AS c FROM file_batch").fetchone()["c"]
        rows = con.execute(
            """
            SELECT file_id, filename, format, sha256, rows, sheets, status, created_at
            FROM file_batch
            ORDER BY created_at DESC, file_id DESC
            LIMIT ? OFFSET ?
            """,
            [limit, offset],
        ).fetchall()
    finally:
        con.close()
    return {
        "limit": limit,
        "offset": offset,
        "total": total,
        "next_offset": offset + limit if offset + limit < total else None,
        "items": [dict(r) for r in rows],
    }


@router.delete("/files/{file_id}")
def delete_file(file_id: str, actor: str = Depends(require_ops)):
    """级联删除单个文件及其全部衍生数据（发布事实、规整记录、物理文件）。"""
    from app.services.intake.file_removal import delete_file as remove_file

    try:
        return remove_file(file_id, actor=actor)
    except FileNotFoundError:
        raise HTTPException(
            404,
            detail={"code": "NOT_FOUND", "message": f"file {file_id} not found"},
        )


@router.get("/tasks")
def list_tasks(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List intake tasks (Wave 1). Status filter: pending/processing/done/failed."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    con = meta_conn()
    try:
        if status:
            total = con.execute(
                "SELECT COUNT(*) FROM intake_task WHERE status=?", [status]
            ).fetchone()[0]
            rows = con.execute(
                """
                SELECT task_id, file_id, filename, task_type, status, progress, message,
                       created_at, heartbeat_at, finished_at
                FROM intake_task WHERE status=?
                ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                [status, limit, offset],
            ).fetchall()
        else:
            total = con.execute("SELECT COUNT(*) FROM intake_task").fetchone()[0]
            rows = con.execute(
                """
                SELECT task_id, file_id, filename, task_type, status, progress, message,
                       created_at, heartbeat_at, finished_at
                FROM intake_task
                ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                [limit, offset],
            ).fetchall()
    finally:
        con.close()
    return {
        "limit": limit,
        "offset": offset,
        "total": total,
        "items": [dict(r) for r in rows],
    }


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    from app.services.intake.error_info import decode_error_message

    con = meta_conn()
    try:
        row = con.execute("SELECT * FROM intake_task WHERE task_id=?", [task_id]).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "task not found"})
    body = dict(row)
    if body.get("status") == "failed":
        body.update(decode_error_message(body.get("message")))
    return body


@router.post("/tasks/{task_id}/retry", status_code=202)
def retry_task(task_id: str, actor: str = Depends(require_ops)):
    try:
        result = intake_svc.retry_parse_evidence(task_id)
    except FileNotFoundError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "task not found"})
    except ValueError as e:
        code = str(e)
        if code == "TASK_NOT_FAILED":
            raise HTTPException(409, detail={"code": "TASK_NOT_FAILED", "message": "task is not failed"})
        if code == "TASK_RETRY_UNSUPPORTED":
            raise HTTPException(
                409,
                detail={"code": "TASK_RETRY_UNSUPPORTED", "message": "only parse_evidence tasks can be retried"},
            )
        if code == "TASK_NOT_RETRYABLE":
            raise HTTPException(409, detail={"code": "TASK_NOT_RETRYABLE", "message": "task is not retryable"})
        raise HTTPException(400, detail={"code": "RETRY_FAILED", "message": code})
    return result
