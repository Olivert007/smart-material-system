# -*- coding: utf-8 -*-
"""Intake pipeline endpoints under /api/v1 (A0-1 split from routes.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app import config
from app.api.auth import require_ops
from app.repositories import meta_conn
from app.services import idempotency as idem_svc
from app.services import staging as staging_svc
from app.services import writer as writer_svc

from app.api.routers._schemas import AnalyzeBody, ConfirmBody, PlanConfirmBody, StageBody

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.post("/intake/analyze/{file_id}")
def intake_analyze(file_id: str, body: AnalyzeBody = AnalyzeBody()):
    """One-shot Step1–4 orchestration (+ optional staging). Never writes DuckDB."""
    from app.services import intake_analyze as analyze_svc

    try:
        if body.async_mode:
            return analyze_svc.enqueue_analyze(
                file_id,
                target_domain=body.target_domain,
                include_stage=body.include_stage,
            )
        return analyze_svc.analyze_file(
            file_id,
            target_domain=body.target_domain,
            include_stage=body.include_stage,
            refresh_profile=body.refresh_profile,
            config_version=body.config_version,
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "file not found"})
    except FileNotFoundError as e:
        raise HTTPException(404, detail={"code": "EVIDENCE_MISSING", "message": str(e)})
    except RuntimeError as e:
        msg = str(e)
        code = msg.split(":", 1)[0] if msg.startswith("FILE_NOT_READY") else "ANALYZE_REFUSED"
        raise HTTPException(409, detail={"code": code, "message": msg})


@router.get("/intake/analyze/{file_id}")
def intake_analyze_get(file_id: str):
    from app.services import intake_analyze as analyze_svc

    row = analyze_svc.get_analyze_report(file_id)
    if not row:
        raise HTTPException(
            404,
            detail={"code": "ANALYZE_NOT_READY", "message": "run POST /intake/analyze first"},
        )
    return row


@router.get("/intake/report/{file_id}")
def intake_report_bundle(file_id: str):
    """Aggregate profile + quality + plan + analyze + staging."""
    from app.services import intake_analyze as analyze_svc

    try:
        return analyze_svc.get_intake_bundle(file_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "file not found"})


@router.get("/intake/conclusion/{file_id}")
def intake_conclusion(file_id: str):
    """上传完成后的业务结论：可进入规整 / 需字段处理 / 需结构确认 / 无法接入。"""
    from app.services.intake import conclusion as conclusion_svc

    try:
        return conclusion_svc.file_conclusion(file_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "file not found"})


@router.get("/intake/profile/{file_id}")
def get_intake_profile(file_id: str):
    """Step1 rule workbook/sheet profile (docs/03 §1.2)."""
    from app.services import profile as profile_svc
    from app.repositories import meta_conn

    con = meta_conn()
    try:
        fb = con.execute("SELECT file_id, status FROM file_batch WHERE file_id=?", [file_id]).fetchone()
    finally:
        con.close()
    if not fb:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "file not found"})
    row = profile_svc.get_workbook_profile(file_id)
    if row:
        return row
    # Lazy build if evidence exists but profile missing (legacy uploads)
    try:
        payload = profile_svc.profile_file_evidence(file_id)
    except FileNotFoundError:
        raise HTTPException(
            404,
            detail={"code": "PROFILE_NOT_READY", "message": "evidence/profile not ready"},
        )
    return {
        "report_id": payload.get("report_id"),
        "file_id": file_id,
        "report_type": "workbook_profile",
        "created_at": None,
        "profile": {k: v for k, v in payload.items() if k not in ("report_id", "file_id")},
    }


@router.get("/intake/quality/{file_id}")
def get_intake_quality(file_id: str):
    """Step3 rule quality precheck report (docs/03 Step3)."""
    from app.services import quality_precheck as quality_svc

    con = meta_conn()
    try:
        fb = con.execute("SELECT file_id FROM file_batch WHERE file_id=?", [file_id]).fetchone()
    finally:
        con.close()
    if not fb:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "file not found"})
    row = quality_svc.get_quality_report(file_id)
    if not row:
        # try from latest staging dry_run
        st = staging_svc.get_staging(file_id)
        if st and isinstance(st.get("dry_run"), dict) and st["dry_run"].get("quality"):
            return {
                "report_id": None,
                "file_id": file_id,
                "report_type": "quality_precheck",
                "created_at": st.get("updated_at"),
                "quality": st["dry_run"]["quality"],
            }
        raise HTTPException(
            404,
            detail={"code": "QUALITY_NOT_READY", "message": "run staging first for quality precheck"},
        )
    return row


@router.post("/intake/plan/{file_id}")
def build_plan(file_id: str, body: PlanConfirmBody | None = None):
    """Step4: build/refresh intake plan draft (meta only)."""
    from app.services import intake_plan as plan_svc

    body = body or PlanConfirmBody()
    try:
        plan = plan_svc.build_intake_plan(file_id, target_domain=body.target_domain)
        rid = plan_svc.save_intake_plan(file_id, plan, status="draft")
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "file not found"})
    except Exception as e:
        raise HTTPException(400, detail={"code": "PLAN_FAILED", "message": str(e)})
    return {
        "report_id": rid,
        "file_id": file_id,
        "plan_status": "draft",
        "plan": plan,
        "mutates_state": False,
    }


@router.get("/intake/plan/{file_id}")
def get_plan(file_id: str):
    from app.services import intake_plan as plan_svc

    row = plan_svc.get_intake_plan(file_id)
    if row:
        return row
    # lazy build
    try:
        plan = plan_svc.build_intake_plan(file_id)
        rid = plan_svc.save_intake_plan(file_id, plan, status="draft")
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "file not found"})
    except Exception as e:
        raise HTTPException(400, detail={"code": "PLAN_FAILED", "message": str(e)})
    return {
        "report_id": rid,
        "file_id": file_id,
        "plan_status": "draft",
        "created_at": None,
        "report_type": "intake_plan",
        "plan": plan,
    }


@router.post("/intake/plan/{file_id}/confirm")
def confirm_plan(file_id: str, body: PlanConfirmBody | None = None, actor: str = Depends(require_ops)):
    """Confirm clean-config draft — meta only, no DuckDB write."""
    from app.services import intake_plan as plan_svc

    body = body or PlanConfirmBody()
    try:
        return plan_svc.confirm_intake_plan(
            file_id, actor=actor, note=body.note, force=bool(body.force)
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "file not found"})
    except RuntimeError as e:
        code = str(e)
        raise HTTPException(409, detail={"code": code, "message": code})


@router.post("/intake/stage/{file_id}")
def stage_file(file_id: str, body: StageBody | None = None):
    body = body or StageBody()
    try:
        return staging_svc.create_staging(
            file_id=file_id,
            config_version=body.config_version,
            target_domain=body.target_domain,
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "file not found"})
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, detail={"code": "STAGE_FAILED", "message": str(e)})


@router.get("/intake/stage/{file_id}")
def get_stage(file_id: str):
    row = staging_svc.get_staging(file_id)
    if not row:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "staging not found"})
    return row


@router.post("/intake/stage/{file_id}/discard")
def discard_stage(file_id: str):
    try:
        ok = staging_svc.discard_staging(file_id)
    except ValueError as e:
        raise HTTPException(409, detail={"code": "STAGE_CONFLICT", "message": str(e)})
    if not ok:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "staging not found"})
    return {"ok": True, "file_id": file_id}


@router.post("/intake/stage/{file_id}/confirm")
def confirm_stage(
    file_id: str,
    request: Request,
    body: ConfirmBody | None = None,
    actor: str = Depends(require_ops),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    body = body or ConfirmBody()
    scope = f"confirm:{file_id}"
    if idempotency_key:
        cached = idem_svc.get(scope, idempotency_key)
        if cached is not None:
            return {**cached, "idempotent": True, "idempotency_replay": True}
    try:
        result = writer_svc.confirm_release(
            file_id=file_id,
            actor=actor,
            expected_version=body.version,
            expected_status=body.expected_status,
            staging_id=body.staging_id,
            target_domain=body.target_domain,
            force=bool(body.force),
            supersedes=body.supersedes,
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "staging not found"})
    except RuntimeError as e:
        code = str(e)
        if code in (
            "STAGE_VERSION_CONFLICT",
            "STAGE_CAS_CONFLICT",
            "STAGE_STATUS_CONFLICT",
            "STAGING_FILE_MISMATCH",
            "GATE_PLAN_UNCONFIRMED",
        ) or code.startswith("GATE_BLOCKED") or "invalid status" in code:
            raise HTTPException(409, detail={"code": code, "message": code})
        raise HTTPException(400, detail={"code": "RELEASE_FAILED", "message": code})
    except Exception as e:
        raise HTTPException(500, detail={"code": "RELEASE_FAILED", "message": str(e)})

    if idempotency_key:
        idem_svc.put(scope, idempotency_key, result, getattr(request.state, "request_id", None))
    return result
