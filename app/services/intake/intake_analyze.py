# -*- coding: utf-8 -*-
"""One-shot intake analyze: Step1–4 orchestration (docs/03 §5 POST /intake/analyze).

Does not write DuckDB. Optional staging dry-run; confirm/release remain separate gates.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pandas as pd

from app.repositories import meta_tx
from app.services.intake.evidence import evidence_path, normalize_tabular, tabular_path


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def _file_status(file_id: str) -> dict[str, Any] | None:
    with meta_tx() as con:
        row = con.execute(
            "SELECT file_id, filename, status, format, rows, sheets FROM file_batch WHERE file_id=?",
            [file_id],
        ).fetchone()
    return dict(row) if row else None


def _run_quality(file_id: str, target_domain: str) -> dict[str, Any]:
    from app.services.govern.mapping import resolve_columns
    from app.services.intake.quality_precheck import run_quality_precheck, save_quality_report

    tab = tabular_path(file_id)
    if not tab.exists():
        return {
            "ok": False,
            "error": "TABULAR_MISSING",
            "message": "tabular parquet missing; cannot quality-precheck",
        }
    df = pd.read_parquet(tab)
    df = normalize_tabular(df, domain=target_domain)
    col_map = resolve_columns(df, target_domain) if target_domain != "generic" else {}
    quality = run_quality_precheck(df, domain=target_domain, col_map=col_map)
    report_id = save_quality_report(file_id, quality)
    return {
        "ok": True,
        "report_id": report_id,
        "quality": {
            "ok": quality.get("ok"),
            "blocking": quality.get("blocking"),
            "issue_total": quality.get("issue_total"),
            "issue_counts": quality.get("issue_counts"),
            "mapped_fields": quality.get("mapped_fields"),
            "domain": quality.get("domain"),
            "row_count": quality.get("row_count"),
        },
    }


def _ensure_profile(file_id: str, *, refresh: bool) -> dict[str, Any]:
    from app.services.intake.profile import (
        get_workbook_profile,
        profile_file_evidence,
        save_workbook_profile,
    )

    if not refresh:
        existing = get_workbook_profile(file_id)
        if existing:
            return {
                "ok": True,
                "report_id": existing.get("report_id"),
                "refreshed": False,
                "workbook": (existing.get("profile") or {}).get("workbook"),
                "sheet_count": len((existing.get("profile") or {}).get("sheets") or []),
            }
    payload = profile_file_evidence(file_id)
    # profile_file_evidence already saves
    return {
        "ok": True,
        "report_id": payload.get("report_id"),
        "refreshed": True,
        "workbook": payload.get("workbook"),
        "sheet_count": len(payload.get("sheets") or []),
    }


def _enqueue_map(file_id: str) -> dict[str, Any]:
    from app.services.govern.map_gov import enqueue_from_file, enqueue_headers

    try:
        out = enqueue_from_file(file_id)
    except FileNotFoundError as e:
        return {"ok": False, "error": "EVIDENCE_MISSING", "message": str(e), "enqueued": 0}

    enqueued = int(out.get("enqueued") or 0)
    fallback = None
    if enqueued == 0:
        tab = tabular_path(file_id)
        if tab.exists():
            cols = [str(c).strip() for c in pd.read_parquet(tab).columns]
            cols = [c for c in cols if c and c.lower() not in {"nan", "unnamed: 0"}]
            if cols:
                fb = enqueue_headers(cols, file_id=file_id, sheet="tabular")
                enqueued = int(fb.get("enqueued") or 0)
                fallback = {
                    "used": True,
                    "headers": cols,
                    "enqueued": enqueued,
                    "reason": "profile_sheets_yielded_zero; used tabular columns",
                }
                out = {**out, "enqueued": enqueued, "fallback": fallback}
    return {
        "ok": True,
        "enqueued": enqueued,
        "sheets": out.get("sheets"),
        "fallback": fallback,
        "hint": out.get("hint"),
    }


def _build_plan(file_id: str, target_domain: str) -> dict[str, Any]:
    from app.services.intake_plan import build_intake_plan, save_intake_plan

    plan = build_intake_plan(file_id, target_domain=target_domain)
    report_id = save_intake_plan(file_id, plan, status="draft")
    gate = plan.get("gate") or {}
    return {
        "ok": True,
        "report_id": report_id,
        "plan_status": "draft",
        "target_table": plan.get("target_table"),
        "target_domain": plan.get("target_domain"),
        "gate": {
            "ok": gate.get("ok"),
            "blockers": gate.get("blockers") or [],
            "warnings": gate.get("warnings") or [],
        },
    }


def _maybe_stage(file_id: str, target_domain: str, config_version: str) -> dict[str, Any]:
    from app.services import staging as staging_svc

    st = staging_svc.create_staging(
        file_id=file_id,
        config_version=config_version,
        target_domain=target_domain,
    )
    return {
        "ok": True,
        "staging_id": st.get("staging_id"),
        "status": st.get("status"),
        "clean_rows": st.get("clean_rows"),
        "blocked_rows": st.get("blocked_rows"),
        "version": st.get("version"),
        "gate_ok": (st.get("impact") or {}).get("gate_ok"),
    }


def analyze_file(
    file_id: str,
    *,
    target_domain: str = "inventory",
    include_stage: bool = True,
    refresh_profile: bool = False,
    config_version: str = "v1",
) -> dict[str, Any]:
    """Run Step1→2→3→4 (+ optional stage). Meta/staging only — never DuckDB."""
    fb = _file_status(file_id)
    if not fb:
        raise KeyError("file not found")
    if fb["status"] not in ("evidence_done", "staged", "released"):
        raise RuntimeError(f"FILE_NOT_READY:{fb['status']}")
    if not evidence_path(file_id).exists():
        raise FileNotFoundError("evidence parquet missing")

    steps: dict[str, Any] = {}
    codes: list[str] = []

    # Step1
    try:
        steps["step1_profile"] = _ensure_profile(file_id, refresh=refresh_profile)
    except Exception as e:
        steps["step1_profile"] = {"ok": False, "error": str(e)[:200]}
        codes.append("PROFILE_FAILED")

    # Step2
    try:
        steps["step2_map_queue"] = _enqueue_map(file_id)
        if int(steps["step2_map_queue"].get("enqueued") or 0) > 0:
            codes.append("MAP_PENDING")
    except Exception as e:
        steps["step2_map_queue"] = {"ok": False, "error": str(e)[:200], "enqueued": 0}
        codes.append("MAP_ENQUEUE_FAILED")

    # Step3
    try:
        steps["step3_quality"] = _run_quality(file_id, target_domain)
        q = steps["step3_quality"].get("quality") or {}
        if q.get("blocking"):
            codes.append("QUALITY_BLOCKING")
        elif not q.get("ok"):
            codes.append("QUALITY_WARN")
    except Exception as e:
        steps["step3_quality"] = {"ok": False, "error": str(e)[:200]}
        codes.append("QUALITY_FAILED")

    # Optional staging dry-run BEFORE plan so Step4 can read dry_run/quality
    if include_stage:
        try:
            steps["stage"] = _maybe_stage(file_id, target_domain, config_version)
        except Exception as e:
            steps["stage"] = {"ok": False, "error": str(e)[:200]}
            codes.append("STAGE_FAILED")

    # Step4 (after stage when included)
    try:
        steps["step4_plan"] = _build_plan(file_id, target_domain)
        gate = steps["step4_plan"].get("gate") or {}
        if not gate.get("ok"):
            codes.append("PLAN_GATE_BLOCKED")
            for b in gate.get("blockers") or []:
                c = b.get("code") if isinstance(b, dict) else None
                if c and c not in codes:
                    codes.append(str(c))
    except Exception as e:
        steps["step4_plan"] = {"ok": False, "error": str(e)[:200]}
        codes.append("PLAN_FAILED")

    # Deduplicate codes while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    codes = uniq

    gate_ok = bool((steps.get("step4_plan") or {}).get("gate", {}).get("ok"))
    blocking = "QUALITY_BLOCKING" in codes or "PLAN_GATE_BLOCKED" in codes or not gate_ok

    next_actions: list[str] = []
    if "MAP_PENDING" in codes:
        next_actions.append("govern_map_pending")
    if blocking:
        next_actions.append("review_gate_or_force_plan_confirm")
    else:
        next_actions.append("confirm_intake_plan")
    if include_stage and (steps.get("stage") or {}).get("ok"):
        next_actions.append("staging_confirm_release")
    elif not include_stage:
        next_actions.append("create_staging")

    summary = {
        "step": "intake_analyze",
        "file_id": file_id,
        "filename": fb.get("filename"),
        "file_status": fb.get("status"),
        "target_domain": target_domain,
        "include_stage": include_stage,
        "ok": all(
            (steps.get(k) or {}).get("ok")
            for k in ("step1_profile", "step2_map_queue", "step3_quality", "step4_plan")
        )
        and (not include_stage or (steps.get("stage") or {}).get("ok")),
        "blocking": blocking,
        "codes": codes,
        "gate_ok": gate_ok,
        "steps": {
            k: {kk: vv for kk, vv in (v or {}).items() if kk not in ("sheets",)}
            for k, v in steps.items()
        },
        "next_actions": next_actions,
        "hint": (
            "analyze 仅写 meta/staging；发布须 plan confirm（若开启）+ staging confirm → writer。"
            "MAP_PENDING 须人工确认后回写 rule_dict。"
        ),
    }
    # keep full steps in saved report (including sheet details)
    report_payload = {**summary, "steps_full": steps}
    report_id = _sid()
    with meta_tx() as con:
        con.execute(
            "DELETE FROM intake_report WHERE file_id=? AND report_type='intake_analyze'",
            [file_id],
        )
        con.execute(
            """
            INSERT INTO intake_report (report_id, file_id, report_type, payload_json)
            VALUES (?, ?, 'intake_analyze', ?)
            """,
            [report_id, file_id, json.dumps(report_payload, ensure_ascii=False, default=str)],
        )

    summary["report_id"] = report_id
    summary["steps"] = steps  # API returns full steps
    return summary


def get_analyze_report(file_id: str) -> dict[str, Any] | None:
    with meta_tx() as con:
        row = con.execute(
            """
            SELECT report_id, file_id, report_type, payload_json, created_at
            FROM intake_report
            WHERE file_id=? AND report_type='intake_analyze'
            ORDER BY created_at DESC LIMIT 1
            """,
            [file_id],
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"] or "{}")
    return {
        "report_id": row["report_id"],
        "file_id": row["file_id"],
        "report_type": row["report_type"],
        "created_at": row["created_at"],
        "analyze": payload,
    }


def get_intake_bundle(file_id: str) -> dict[str, Any]:
    """Aggregate Step1–4 + analyze + staging for GET /intake/report/{file_id}."""
    from app.services.intake_plan import get_intake_plan
    from app.services.intake.profile import get_workbook_profile
    from app.services.intake.quality_precheck import get_quality_report
    from app.services.staging import get_staging

    fb = _file_status(file_id)
    if not fb:
        raise KeyError("file not found")

    return {
        "file_id": file_id,
        "file": fb,
        "profile": get_workbook_profile(file_id),
        "quality": get_quality_report(file_id),
        "plan": get_intake_plan(file_id),
        "analyze": get_analyze_report(file_id),
        "staging": get_staging(file_id),
    }


def enqueue_analyze(
    file_id: str,
    *,
    target_domain: str = "inventory",
    include_stage: bool = True,
) -> dict[str, Any]:
    """Queue async analyze task (worker picks up task_type=analyze)."""
    fb = _file_status(file_id)
    if not fb:
        raise KeyError("file not found")
    if fb["status"] not in ("evidence_done", "staged", "released"):
        raise RuntimeError(f"FILE_NOT_READY:{fb['status']}")
    task_id = _sid()
    msg = json.dumps(
        {
            "target_domain": target_domain,
            "include_stage": include_stage,
        },
        ensure_ascii=False,
    )
    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO intake_task (task_id, file_id, filename, task_type, status, progress, message, attempt)
            VALUES (?, ?, ?, 'analyze', 'pending', 0, ?, 0)
            """,
            [task_id, file_id, fb.get("filename") or file_id, msg[:200]],
        )
    return {
        "file_id": file_id,
        "task_id": task_id,
        "status": "pending",
        "task_type": "analyze",
        "target_domain": target_domain,
        "include_stage": include_stage,
    }


def process_analyze_task(task_id: str) -> None:
    from app.services.intake import _now, touch_heartbeat

    with meta_tx() as con:
        task = con.execute("SELECT * FROM intake_task WHERE task_id=?", [task_id]).fetchone()
        if not task or task["task_type"] != "analyze":
            return
        file_id = task["file_id"]
        try:
            opts = json.loads(task["message"] or "{}")
            if not isinstance(opts, dict) or "target_domain" not in opts:
                opts = {"target_domain": "inventory", "include_stage": True}
        except json.JSONDecodeError:
            opts = {"target_domain": "inventory", "include_stage": True}
        con.execute(
            """
            UPDATE intake_task
            SET status='processing', progress=10, heartbeat_at=?, attempt=attempt+1, message='analyzing'
            WHERE task_id=?
            """,
            [_now(), task_id],
        )

    try:
        touch_heartbeat(task_id, message="analyze step1-4")
        out = analyze_file(
            file_id,
            target_domain=str(opts.get("target_domain") or "inventory"),
            include_stage=bool(opts.get("include_stage", True)),
        )
        with meta_tx() as con:
            con.execute(
                """
                UPDATE intake_task
                SET status='done', progress=100, message=?, finished_at=?, heartbeat_at=?
                WHERE task_id=?
                """,
                [
                    (
                        f"analyze ok={out.get('ok')} blocking={out.get('blocking')} "
                        f"codes={','.join(out.get('codes') or [])} report={out.get('report_id')}"
                    )[:200],
                    _now(),
                    _now(),
                    task_id,
                ],
            )
    except Exception as e:
        with meta_tx() as con:
            con.execute(
                """
                UPDATE intake_task
                SET status='failed', message=?, finished_at=?, heartbeat_at=?
                WHERE task_id=?
                """,
                [str(e)[:500], _now(), _now(), task_id],
            )
