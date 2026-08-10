# -*- coding: utf-8 -*-
"""Step4 intake plan draft + gate preview (docs/03 §1.1 / §4.5).

Rule-only config draft. Confirming a plan writes meta only — never DuckDB.
Business write remains staging confirm → writer.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from app import config
from app.repositories import meta_tx

# std_field → suggested clean primitive (docs/03 §1.1)
_CLEAN_HINT: dict[str, str] = {
    "material_code": "code",
    "asset_code": "code",
    "stock_qty": "num_unit",
    "quantity": "num_unit",
    "quota_qty": "num_unit",
    "qty_in": "num_unit",
    "qty_out": "num_unit",
    "unit_price": "num",
    "total_price": "num",
    "purchase_date": "date",
    "flow_date": "date",
    "flow_in_text": "flow_text",
    "flow_out_text": "flow_text",
    "material_name": "norm",
    "asset_name": "norm",
    "item_name": "norm",
    "spec": "norm",
    "specification": "norm",
    "unit": "norm",
    "location": "norm",
    "region": "norm",
    "category": "norm",
    "remark": "norm",
    "ignore": "drop",
}

_TARGET_TABLE: dict[str, str] = {
    "inventory": "fact_inventory",
    "asset": "fact_asset",
    "demand": "fact_demand",
    "stock_flow": "fact_stock_flow",
    "quota": "fact_quota_adjust",
}

_MASTER_STD = {
    "code": ("material_code", "asset_code"),
    "name": ("material_name", "asset_name", "item_name"),
    "spec": ("spec", "specification"),
}


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:12]


def _header_for_std(col_map: dict[str, str], std: str) -> str | None:
    return col_map.get(std)


def build_sheet_config(
    *,
    source: str,
    sheet: str,
    structure: str,
    adapter: str,
    header_row: int | None,
    col_map: dict[str, str],
    dedup_std: list[str],
    target_domain: str,
    role_hint: str | None = None,
) -> dict[str, Any]:
    """Build one sheet-level clean config (03 §1.1)."""
    columns = []
    for std, header in col_map.items():
        columns.append(
            {
                "header": header,
                "std_field": std,
                "clean": _CLEAN_HINT.get(std, "norm"),
            }
        )
    master: dict[str, str] = {}
    for key, stds in _MASTER_STD.items():
        for s in stds:
            h = _header_for_std(col_map, s)
            if h:
                master[key] = h
                break
    dedup_headers = []
    for s in dedup_std:
        h = _header_for_std(col_map, s)
        if h:
            dedup_headers.append(h)
    if not dedup_headers and master.get("code"):
        dedup_headers = [master["code"]]

    cfg: dict[str, Any] = {
        "source": source,
        "sheet": sheet,
        "structure": structure or "标准纵向",
        "adapter": adapter or "none",
        "header_row": header_row,
        "role_hint": role_hint,
        "target_domain": target_domain,
        "target_table": _TARGET_TABLE.get(target_domain, "fact_inventory"),
        "columns": columns,
        "master": master,
        "dedup": dedup_headers,
    }
    # flow_config when flow text columns present
    flow_cols = []
    if "flow_in_text" in col_map:
        flow_cols.append(
            {
                "header": col_map["flow_in_text"],
                "flow_type": "IN",
                "qty_column": col_map.get("qty_in"),
            }
        )
    if "flow_out_text" in col_map:
        flow_cols.append(
            {
                "header": col_map["flow_out_text"],
                "flow_type": "OUT",
                "qty_column": col_map.get("qty_out"),
            }
        )
    if flow_cols:
        cfg["flow_config"] = {"flow_columns": flow_cols}
    return cfg


def gate_preview(
    *,
    plan: dict[str, Any],
    quality: dict[str, Any] | None = None,
    map_pending_count: int = 0,
) -> dict[str, Any]:
    """Confirm-gate checks (mutates_state=false)."""
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    sheets = plan.get("sheets") or []
    if not sheets:
        blockers.append({"code": "NO_SHEETS", "message": "计划中无可用 sheet 配置"})

    for sc in sheets:
        if not sc.get("columns"):
            blockers.append(
                {
                    "code": "NO_COLUMNS",
                    "message": f"sheet={sc.get('sheet')} 无列映射",
                }
            )
        if sc.get("role_hint") in {"reference", "history_copy", "empty"}:
            warnings.append(
                {
                    "code": "SKIP_ROLE",
                    "message": f"sheet={sc.get('sheet')} role={sc.get('role_hint')} 建议跳过入库",
                }
            )
        # region bounds if present
        for reg in sc.get("regions") or []:
            sr, hr, er = reg.get("start_row"), reg.get("header_row"), reg.get("end_row")
            if None not in (sr, hr, er) and not (sr <= hr <= er):
                blockers.append(
                    {
                        "code": "REGION_BOUNDS",
                        "message": f"region {reg.get('name')} bounds invalid",
                    }
                )

    if quality and quality.get("blocking"):
        blockers.append(
            {
                "code": "QUALITY_BLOCKING",
                "message": f"质量预检 blocking；issues={quality.get('issue_total')}",
            }
        )
    elif quality and int(quality.get("issue_total") or 0) > 0:
        warnings.append(
            {
                "code": "QUALITY_WARN",
                "message": f"质量问题 {quality.get('issue_total')}（非 blocking）",
            }
        )

    # P1-4 中危1：金额列完整性硬核验（quality.money）
    money = (quality or {}).get("money") or {}
    if money.get("severity") == "block":
        blockers.append(
            {
                "code": "MONEY_COLS_MISSING",
                "message": f"金额列缺失/未映射：{money.get('detail') or ''}",
            }
        )
    elif money.get("severity") == "warn":
        warnings.append(
            {
                "code": "MONEY_WARN",
                "message": f"金额口径缺失：{money.get('detail') or ''}",
            }
        )

    if map_pending_count > 0:
        warnings.append(
            {
                "code": "MAP_PENDING",
                "message": f"仍有 {map_pending_count} 条表头映射待确认",
            }
        )

    ok = len(blockers) == 0
    return {
        "ok": ok,
        "can_confirm_release": ok,
        "blockers": blockers,
        "warnings": warnings,
        "enforce": bool(getattr(config, "INTAKE_GATE_ENFORCE", True)),
    }


def build_intake_plan(
    file_id: str,
    *,
    target_domain: str = "inventory",
) -> dict[str, Any]:
    """Assemble plan from profile + latest staging dry_run (+ quality)."""
    from app.services.profile import get_workbook_profile
    from app.services.quality_precheck import get_quality_report
    from app.services.staging import get_staging
    from app.services.map_gov import list_pending

    with meta_tx() as con:
        fb = con.execute("SELECT * FROM file_batch WHERE file_id=?", [file_id]).fetchone()
    if not fb:
        raise KeyError("file not found")

    staging = get_staging(file_id)
    dry = (staging or {}).get("dry_run") or {}
    col_map = dict(dry.get("column_mapping") or {})
    domain = dry.get("target_domain") or target_domain or "inventory"
    quality_wrap = get_quality_report(file_id)
    quality = (quality_wrap or {}).get("quality") or dry.get("quality")

    prof_wrap = get_workbook_profile(file_id)
    sheets_prof = ((prof_wrap or {}).get("profile") or {}).get("sheets") or []

    dedup_std = list((quality or {}).get("suggested_dedup") or [])
    source_name = fb["filename"] or file_id

    sheet_cfgs: list[dict[str, Any]] = []
    if sheets_prof:
        for sp in sheets_prof:
            role = sp.get("role_hint")
            if role in {"empty", "reference", "history_copy"}:
                # still record skip sheet briefly
                sheet_cfgs.append(
                    {
                        "source": source_name,
                        "sheet": sp.get("sheet"),
                        "structure": sp.get("structure_hint") or "report_only",
                        "adapter": sp.get("adapter_hint") or "none",
                        "header_row": (sp.get("header_row_candidates") or [None])[0],
                        "role_hint": role,
                        "target_domain": domain,
                        "target_table": None,
                        "columns": [],
                        "master": {},
                        "dedup": [],
                        "skip": True,
                    }
                )
                continue
            hdr = (sp.get("header_row_candidates") or [None])[0]
            # Prefer staging col_map for the active domain sheet; reuse for detail sheets
            sheet_cfgs.append(
                build_sheet_config(
                    source=source_name,
                    sheet=str(sp.get("sheet")),
                    structure=str(sp.get("structure_hint") or "标准纵向"),
                    adapter=str(sp.get("adapter_hint") or "none"),
                    header_row=int(hdr) if hdr is not None else None,
                    col_map=col_map,
                    dedup_std=dedup_std,
                    target_domain=domain,
                    role_hint=role,
                )
            )
    else:
        sheet_cfgs.append(
            build_sheet_config(
                source=source_name,
                sheet="Sheet1",
                structure="标准纵向",
                adapter="none",
                header_row=1,
                col_map=col_map,
                dedup_std=dedup_std,
                target_domain=domain,
                role_hint="detail",
            )
        )

    pending = list_pending(status="pending", file_id=file_id, limit=1)
    # also count global pending without file filter for ad-hoc
    pending_all = list_pending(status="pending", limit=1)
    map_pending_count = int(pending.get("total") or 0)
    if map_pending_count == 0:
        map_pending_count = int(pending_all.get("total") or 0)

    plan: dict[str, Any] = {
        "step": "intake_plan",
        "source": "rule",
        "file_id": file_id,
        "filename": source_name,
        "target_domain": domain,
        "target_table": _TARGET_TABLE.get(domain),
        "config_version": (staging or {}).get("config_version") or "v1",
        "sheets": sheet_cfgs,
        "quality_summary": {
            "blocking": bool((quality or {}).get("blocking")),
            "issue_total": int((quality or {}).get("issue_total") or 0),
            "issue_counts": (quality or {}).get("issue_counts") or {},
        },
        "map_pending_count": map_pending_count,
        "mutates_state": False,
        "hint": "接入建议草案（规则）；确认计划只写 meta，业务库仍须 Staging 确认门",
    }
    plan["gate"] = gate_preview(
        plan=plan, quality=quality, map_pending_count=map_pending_count
    )
    return plan


def save_intake_plan(file_id: str, plan: dict[str, Any], *, status: str = "draft") -> str:
    report_id = _sid()
    payload = {**plan, "plan_status": status}
    with meta_tx() as con:
        con.execute(
            "DELETE FROM intake_report WHERE file_id=? AND report_type='intake_plan'",
            [file_id],
        )
        con.execute(
            """
            INSERT INTO intake_report (report_id, file_id, report_type, payload_json)
            VALUES (?, ?, 'intake_plan', ?)
            """,
            [report_id, file_id, json.dumps(payload, ensure_ascii=False, default=str)],
        )
    return report_id


def get_intake_plan(file_id: str) -> dict[str, Any] | None:
    with meta_tx() as con:
        row = con.execute(
            """
            SELECT report_id, file_id, report_type, payload_json, created_at
            FROM intake_report
            WHERE file_id=? AND report_type='intake_plan'
            ORDER BY created_at DESC LIMIT 1
            """,
            [file_id],
        ).fetchone()
    if not row:
        return None
    plan = json.loads(row["payload_json"] or "{}")
    return {
        "report_id": row["report_id"],
        "file_id": row["file_id"],
        "report_type": row["report_type"],
        "created_at": row["created_at"],
        "plan_status": plan.get("plan_status") or "draft",
        "plan": plan,
    }


def confirm_intake_plan(
    file_id: str,
    *,
    actor: str,
    note: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """Human confirms clean config draft → meta only (C3/C5)."""
    wrapped = get_intake_plan(file_id)
    if not wrapped:
        plan = build_intake_plan(file_id)
        save_intake_plan(file_id, plan, status="draft")
        wrapped = get_intake_plan(file_id)
    assert wrapped
    plan = wrapped["plan"]
    gate = plan.get("gate") or gate_preview(plan=plan)
    if (not gate.get("ok")) and not force:
        raise RuntimeError("PLAN_GATE_BLOCKED")

    plan["plan_status"] = "confirmed"
    plan["confirmed_by"] = actor
    plan["confirm_note"] = (note or "")[:200]
    plan["force_confirm"] = bool(force)
    report_id = save_intake_plan(file_id, plan, status="confirmed")

    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('intake_plan', ?, ?, ?, ?)
            """,
            [
                json.dumps(
                    {
                        "file_id": file_id,
                        "target_domain": plan.get("target_domain"),
                        "target_table": plan.get("target_table"),
                        "force": force,
                    },
                    ensure_ascii=False,
                )[:200],
                "force_accepted" if force else "accepted",
                (note or "")[:200],
                actor,
            ],
        )

    return {
        "ok": True,
        "file_id": file_id,
        "report_id": report_id,
        "plan_status": "confirmed",
        "mutates_state": False,
        "gate": gate,
        "actor": actor,
        "hint": "计划已确认（仅 meta）；发布业务库请再走 Staging confirm",
    }


def assert_release_gate(
    file_id: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Raise RuntimeError GATE_* if release should be blocked."""
    if not getattr(config, "INTAKE_GATE_ENFORCE", True):
        return {"ok": True, "skipped": True}
    if force:
        return {"ok": True, "forced": True}

    wrapped = get_intake_plan(file_id)
    if wrapped is None:
        # build ephemeral gate from staging quality
        plan = build_intake_plan(file_id)
        gate = plan.get("gate") or {}
        if not gate.get("ok"):
            raise RuntimeError("GATE_BLOCKED:" + ",".join(b["code"] for b in gate.get("blockers") or []))
        if getattr(config, "INTAKE_REQUIRE_PLAN_CONFIRM", True):
            raise RuntimeError("GATE_PLAN_UNCONFIRMED")
        return {"ok": True, "plan_status": "missing_allowed"}

    plan = wrapped["plan"]
    status = wrapped.get("plan_status") or plan.get("plan_status") or "draft"
    gate = plan.get("gate") or gate_preview(plan=plan)
    if not gate.get("ok"):
        raise RuntimeError("GATE_BLOCKED:" + ",".join(b["code"] for b in gate.get("blockers") or []))
    if getattr(config, "INTAKE_REQUIRE_PLAN_CONFIRM", True) and status != "confirmed":
        raise RuntimeError("GATE_PLAN_UNCONFIRMED")
    return {"ok": True, "plan_status": status}
