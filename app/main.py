# -*- coding: utf-8 -*-
"""FastAPI entry — Phase A trusted pipeline + F2 static SPA."""
from __future__ import annotations

import ipaddress
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app import config
from app.api.routes import router
from app.api.events import router as events_router
from app.api.legacy import router as legacy_router
from app.repositories import init_meta
from app.repositories.db import readonly_probe
from app.services.intake import recover_orphan_tasks
from app.services.govern.flow_config import ensure_flow_configs_seed
from app.services.metrics import ensure_metrics_seed
from app.services.fewshot import ensure_sql_fewshot_seed
from app.services.value_validator import ensure_value_rule_seed
from app.services.govern.rule_dict import ensure_seed_rules
from app.services.report_runner import ensure_report_seed
from app.services.writer import compensate_releasing
from app.workers.intake_worker import worker

APP_VERSION = "0.6.1-ocr-eval"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


# F4 LAN 来源限制（docs/11 F4 / 01 待处理 #12）：config.ALLOWED_CIDRS 为空 = 关闭；
# 非空时仅放行回环地址与命中 CIDR 的客户端 IP，其余 403 LAN_FORBIDDEN
_ALLOWED_NETWORKS: list = []
for _cidr in config.ALLOWED_CIDRS:
    try:
        _ALLOWED_NETWORKS.append(ipaddress.ip_network(_cidr, strict=False))
    except ValueError:
        pass


class LanGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _ALLOWED_NETWORKS:
            host = (request.client.host if request.client else "") or ""
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                ip = None
            allowed = ip is not None and (
                ip.is_loopback or any(ip in net for net in _ALLOWED_NETWORKS)
            )
            if not allowed:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "LAN_FORBIDDEN",
                        "code": "LAN_FORBIDDEN",
                        "message": "client not in ALLOWED_CIDRS",
                        "details": {"client": host},
                    },
                )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_meta()
    ensure_metrics_seed()
    ensure_sql_fewshot_seed()
    ensure_flow_configs_seed()
    ensure_value_rule_seed()
    ensure_seed_rules()
    ensure_report_seed()
    recover_orphan_tasks()
    compensate_releasing()
    if os.environ.get("DISABLE_INTAKE_WORKER", "0") != "1":
        worker.start()
    yield
    worker.stop()


app = FastAPI(
    title="物资数据规整系统",
    version=APP_VERSION,
    description="Trusted pipeline + F2 SPA: SQLite meta, unique writer, idempotent release, AST query",
    lifespan=lifespan,
)
app.add_middleware(LanGuardMiddleware)
app.add_middleware(RequestIdMiddleware)
app.include_router(router)
app.include_router(events_router)
# A2-1: legacy endpoints always mounted (stable OpenAPI), handlers return 404
# when their gate flag is off, so a default deployment does not expose them.
app.include_router(legacy_router)


def _error_body(request: Request, *, code: str, message: str, details: dict | None = None) -> dict:
    return {
        "error": code,
        "message": message,
        "code": code,
        "details": details or {},
        "request_id": getattr(request.state, "request_id", None),
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or "HTTP_ERROR")
        message = str(detail.get("message") or code)
        details = detail.get("details") if isinstance(detail.get("details"), dict) else {
            k: v for k, v in detail.items() if k not in ("code", "message")
        }
    else:
        code = "HTTP_ERROR"
        message = str(detail)
        details = {}
    body = _error_body(request, code=code, message=message, details=details)
    return JSONResponse(status_code=exc.status_code, content=body, headers={"X-Request-ID": body["request_id"] or ""})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = _error_body(
        request,
        code="VALIDATION_ERROR",
        message="request validation failed",
        details={"errors": exc.errors()},
    )
    return JSONResponse(status_code=422, content=body, headers={"X-Request-ID": body["request_id"] or ""})


@app.get("/health/live")
def health_live():
    return {"status": "live"}


@app.get("/health/ready")
def health_ready():
    # A2-2: real probes instead of hardcoded True.
    # biz_db: if the file exists, a read-only SELECT 1 must pass (detects lock/corrupt);
    # if it does not exist yet, it is bootstrapped lazily on first biz_conn — treat as ready.
    biz_path = Path(config.BIZ_DB)
    biz_ok = True
    if biz_path.exists():
        try:
            with readonly_probe() as con:
                con.execute("SELECT 1").fetchall()
        except Exception:
            biz_ok = False

    worker_ok = worker.is_alive()
    if os.environ.get("DISABLE_INTAKE_WORKER", "0") == "1":
        # Offline compose: intake worker runs in a separate container.
        worker_ok = True
    ready = biz_ok and worker_ok
    body = {
        "status": "ready" if ready else "not_ready",
        "meta_db": Path(config.META_DB).exists(),
        "biz_db": biz_ok,
        "worker": worker_ok,
        "frontend_dist": config.FRONTEND_DIST.is_dir() and (config.FRONTEND_DIST / "index.html").exists(),
        "version": APP_VERSION,
    }
    return JSONResponse(status_code=200 if ready else 503, content=body)


@app.get("/api")
def api_root():
    return {
        "name": "物资数据规整系统 API",
        "version": APP_VERSION,
        "phase": "A",
        "frontend": "F3",
        "docs": "/docs",
        "health": ["/health/live", "/health/ready"],
        "api": "/api/v1",
        "events": "/events/tasks/{task_id}",
    }


def _mount_spa() -> None:
    dist = config.FRONTEND_DIST
    index = dist / "index.html"
    if not index.exists():
        @app.get("/")
        def root_fallback():
            return {
                "name": "物资数据规整系统 API",
                "version": APP_VERSION,
                "hint": "frontend/dist missing — run: cd frontend && npm run build",
                "docs": "/docs",
                "api": "/api/v1",
            }

        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/")
    def spa_index():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Never steal API / health / OpenAPI surfaces
        blocked = (
            "api/",
            "api",
            "health/",
            "health",
            "events/",
            "events",
            "docs",
            "redoc",
            "openapi.json",
            "assets/",
        )
        if full_path.startswith(blocked) or full_path in {"docs", "redoc", "openapi.json"}:
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "not found"})
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


_mount_spa()
