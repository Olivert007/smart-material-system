# -*- coding: utf-8 -*-
"""Staging + dry-run (Phase A: rule-only, no LLM)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app import config
from app.repositories import meta_tx
from app.services.evidence import evidence_path, tabular_path
from app.services.jsonutil import json_safe
from app.services.mapping import resolve_columns


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _sid() -> str:
    return uuid.uuid4().hex[:12]


def _clean_sample(clean: pd.DataFrame, n: int = 20) -> list[dict]:
    """规整后样本行（JSON-safe），供 dry_run 前端预览使用。"""
    if len(clean) == 0:
        return []
    part = clean.head(n).astype(object)
    return json_safe(part.where(pd.notna(part), None).to_dict(orient="records"))


def create_staging(
    *,
    file_id: str,
    config_version: str = "v1",
    target_domain: str = "inventory",
) -> dict:
    with meta_tx() as con:
        fb = con.execute("SELECT * FROM file_batch WHERE file_id=?", [file_id]).fetchone()
        if not fb:
            raise KeyError("file not found")
        if fb["status"] not in ("evidence_done", "staged", "released"):
            raise ValueError(f"file status not ready for staging: {fb['status']}")
        source_hash = fb["sha256"] or ""
        file_format = fb["format"]
        file_sheets = int(fb["sheets"] or 0)
        existing = con.execute(
            """
            SELECT * FROM staging_record
            WHERE source_file_hash=? AND config_version=? AND target_domain=?
            """,
            [source_hash, config_version, target_domain],
        ).fetchone()
        # Cache only in-flight/current STAGED; allow RELEASED restage after mapping fixes
        if existing and existing["status"] in ("STAGED", "RELEASING"):
            d = dict(existing)
            d["dry_run"] = json.loads(d.pop("dry_run_json") or "{}")
            d["impact"] = json.loads(d.pop("impact_json") or "{}")
            return d

    tab = tabular_path(file_id)
    ev = evidence_path(file_id)
    stored = Path(fb["stored_path"] or "")
    # stock_flow: rebuild multi-sheet tabular from original workbook when possible
    if target_domain == "stock_flow" and stored.exists() and stored.suffix.lower() in {
        ".xlsx",
        ".xls",
        ".xlsb",
        ".xlsm",
        ".ods",
    }:
        from app.services.evidence import load_stock_flow_tabular, save_evidence

        flow_df = load_stock_flow_tabular(stored)
        if flow_df is not None and len(flow_df) > 0:
            save_evidence(
                pd.read_parquet(ev) if ev.exists() else flow_df,
                file_id,
                tabular=flow_df,
            )
            df = flow_df
            clean = df
            blocked = df.iloc[0:0]
            col_map = resolve_columns(df, target_domain)
            payload_kind = "tabular"
        elif tab.exists():
            df = pd.read_parquet(tab)
            from app.services.evidence import normalize_tabular

            df = normalize_tabular(df, domain=target_domain)
            clean = df
            blocked = df.iloc[0:0]
            col_map = resolve_columns(df, target_domain)
            payload_kind = "tabular"
        else:
            raise FileNotFoundError("stock_flow tabular missing")
    elif tab.exists():
        df = pd.read_parquet(tab)
        from app.services.evidence import normalize_tabular
        from app.services.govern.flow_config import ledger_sheet_names

        # T3.2: 4-sheet 台账按域路由过滤（仅当文件内实际存在路由 sheet；否则保持旧行为）
        if "sheet" in df.columns and target_domain in ("inventory", "asset"):
            keep = [s for s in ledger_sheet_names(target_domain) if s]
            if keep:
                present = {str(p).strip() for p in df["sheet"].astype(str).tolist()}
                matched = [s for s in keep if any(s in p or p in s for p in present)]
                if matched:
                    import re as _re

                    pat = "|".join(_re.escape(s) for s in matched)
                    df = df[
                        df["sheet"].astype(str).str.contains(pat, case=False, na=False, regex=True)
                    ].reset_index(drop=True)
        df = normalize_tabular(df, domain=target_domain)
        clean = df
        blocked = df.iloc[0:0]
        col_map = resolve_columns(df, target_domain) if target_domain != "generic" else {}
        payload_kind = "tabular"
    else:
        if not ev.exists():
            raise FileNotFoundError("evidence parquet missing")
        df = pd.read_parquet(ev)
        clean = df[df["value_type"] != "marker"] if "value_type" in df.columns else df
        blocked = df[df["value_type"] == "marker"] if "value_type" in df.columns else df.iloc[0:0]
        col_map = {}
        payload_kind = "cell_evidence"

    blocked_details: list[dict] = []
    if payload_kind == "cell_evidence" and len(blocked) > 0:
        for _, row in blocked.iterrows():
            blocked_details.append(
                {
                    "source_row": int(row["row"])
                    if "row" in blocked.columns and pd.notna(row.get("row"))
                    else None,
                    "header": str(row.get("col") or ""),
                    "reason_code": "CELL_MARKER",
                    "reason_detail": str(row.get("raw_value") or "marker")[:200],
                    "raw_value": str(row.get("raw_value") or "")[:200],
                }
            )

    raw_snapshot_path = None
    if payload_kind == "tabular":
        staging_dir = config.STAGING / file_id
        staging_dir.mkdir(parents=True, exist_ok=True)
        raw_snapshot_path = staging_dir / f"{config_version}_{target_domain}_raw.parquet"
        df.to_parquet(raw_snapshot_path, index=False)

    if payload_kind == "tabular" and target_domain != "generic" and col_map:
        from app.services.value_validator import apply_checks, clean_ledger_qtys

        # T5.2 (LD-4, 2026-08-10)：normalize → resolve → clean → apply_checks。
        # 先清洗台账数量/单位（"50+"→50、"120对"→120、"已取消，0"→0、"一年一次"→1、
        # "无定额"/"/"→空），再校验；不可解析值由 apply_checks 拦截（VALUE_RANGE）。
        clean = clean_ledger_qtys(clean, col_map=col_map)
        clean, blocked_val, details_val = apply_checks(
            clean, domain=target_domain, col_map=col_map
        )
        if len(blocked_val):
            blocked = (
                pd.concat([blocked, blocked_val], ignore_index=True)
                if len(blocked)
                else blocked_val
            )
        blocked_details.extend(details_val)

    fingerprint = f"{source_hash}:{file_format}:{file_sheets}:{config_version}"
    flow_stats = None
    pending_n = 0
    if target_domain == "stock_flow" and payload_kind == "tabular":
        from app.services.mapping import build_stock_flow_bundle

        _table, l1_rows, pending, flow_stats = build_stock_flow_bundle(
            clean,
            file_id=file_id,
            release_id="preview",
            source_file=fb["filename"] or file_id,
        )
        pending_n = len(pending)
        with meta_tx() as con:
            con.execute(
                "DELETE FROM flow_pending WHERE file_id=? AND status='pending'", [file_id]
            )
            for p in pending:
                pid = _sid()
                con.execute(
                    """
                    INSERT INTO flow_pending (
                        pending_id, file_id, source_sheet, source_row, source_segment,
                        flow_type, text_raw, text_norm, parse_level, suggested_json, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    [
                        pid,
                        file_id,
                        p.get("source_sheet"),
                        p.get("source_row"),
                        p.get("source_segment"),
                        p.get("flow_type"),
                        p.get("text_raw"),
                        p.get("text_norm"),
                        p.get("parse_level"),
                        json.dumps(p.get("suggested_json") or {}, ensure_ascii=False, default=str),
                    ],
                )
        projected_clean = len(l1_rows)
    else:
        projected_clean = int(len(clean))

    quality = None
    if payload_kind == "tabular" and target_domain != "generic":
        from app.services.quality_precheck import run_quality_precheck, save_quality_report

        quality = run_quality_precheck(clean, domain=target_domain, col_map=col_map)
        save_quality_report(file_id, quality)
        qmap = {
            "missing_required": "MISSING_COL",
            "required_unmapped": "REQUIRED_UNMAPPED",
            "duplicate_pk": "OTHER",
            "qty_year_like": "VALUE_RANGE",
            "qty_negative": "VALUE_RANGE",
            "qty_non_numeric": "TYPE_ERROR",
            "empty_row": "OTHER",
        }
        for issue in quality.get("issues_sample") or []:
            code = str(issue.get("code") or "")
            blocked_details.append(
                {
                    "source_row": issue.get("row"),
                    "header": ",".join(issue.get("fields") or [])[:120],
                    "reason_code": qmap.get(code, (code.upper() or "OTHER")),
                    "reason_detail": str(issue.get("detail") or code)[:200],
                    "raw_value": None,
                }
            )

    dry_run = {
        "mutates_state": False,
        "payload_kind": payload_kind,
        "raw_payload_path": str(raw_snapshot_path) if raw_snapshot_path else None,
        "column_mapping": col_map,
        "projected_clean_rows": projected_clean,
        "projected_blocked_rows": int(len(blocked)),
        "blocked_detail_count": len(blocked_details),
        "target_domain": target_domain,
        "config_version": config_version,
        "flow_parse": flow_stats,
        "flow_pending": pending_n,
        "quality": quality,
        "clean_columns": [str(c) for c in clean.columns],
        "clean_sample": _clean_sample(clean),
    }
    impact = {
        "will_insert": projected_clean,
        "will_update": 0,
        "conflicts": [],
        "flow_pending": pending_n,
        "quality_blocking": bool(quality.get("blocking")) if quality else False,
        "quality_issue_total": int(quality.get("issue_total") or 0) if quality else 0,
        "blocked_detail_count": len(blocked_details),
    }
    staging_dir = config.STAGING / file_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    payload_path = staging_dir / f"{config_version}_{target_domain}.parquet"
    clean.to_parquet(payload_path, index=False)

    staging_id = _sid()
    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO staging_record (
                staging_id, file_id, config_version, target_domain, source_file_hash,
                status, fingerprint, dry_run_json, impact_json, clean_rows, blocked_rows, version
            ) VALUES (?, ?, ?, ?, ?, 'STAGED', ?, ?, ?, ?, ?, 1)
            ON CONFLICT(source_file_hash, config_version, target_domain) DO UPDATE SET
                status='STAGED',
                fingerprint=excluded.fingerprint,
                dry_run_json=excluded.dry_run_json,
                impact_json=excluded.impact_json,
                clean_rows=excluded.clean_rows,
                blocked_rows=excluded.blocked_rows,
                version=staging_record.version+1,
                updated_at=datetime('now'),
                staging_id=excluded.staging_id,
                release_id=NULL
            """,
            [
                staging_id,
                file_id,
                config_version,
                target_domain,
                source_hash,
                fingerprint,
                json.dumps(dry_run, ensure_ascii=False),
                json.dumps(impact, ensure_ascii=False),
                projected_clean,
                int(len(blocked)),
            ],
        )
        con.execute("UPDATE file_batch SET status='staged' WHERE file_id=?", [file_id])
        row = con.execute(
            """
            SELECT * FROM staging_record
            WHERE source_file_hash=? AND config_version=? AND target_domain=?
            """,
            [source_hash, config_version, target_domain],
        ).fetchone()
        report_id = _sid()
        con.execute(
            """
            INSERT INTO intake_report (report_id, file_id, report_type, payload_json)
            VALUES (?, ?, 'staging', ?)
            """,
            [
                report_id,
                file_id,
                json.dumps(
                    {"staging_id": row["staging_id"], "dry_run": dry_run, "impact": impact},
                    ensure_ascii=False,
                ),
            ],
        )

    from app.services.quality import replace_blocked_details

    detail_n = replace_blocked_details(
        staging_id=row["staging_id"],
        file_id=file_id,
        target_domain=target_domain,
        details=blocked_details,
    )
    dry_run["blocked_detail_count"] = detail_n
    impact["blocked_detail_count"] = detail_n

    plan = None
    plan_report_id = None
    try:
        from app.services.intake_plan import build_intake_plan, save_intake_plan

        plan = build_intake_plan(file_id, target_domain=target_domain)
        plan_report_id = save_intake_plan(file_id, plan, status="draft")
        dry_run["intake_plan"] = {
            "report_id": plan_report_id,
            "plan_status": "draft",
            "gate": plan.get("gate"),
            "target_table": plan.get("target_table"),
            "sheets": len(plan.get("sheets") or []),
        }
        impact["gate_ok"] = bool((plan.get("gate") or {}).get("ok"))
        with meta_tx() as con:
            con.execute(
                """
                UPDATE staging_record SET dry_run_json=?, impact_json=?, updated_at=datetime('now')
                WHERE staging_id=?
                """,
                [
                    json.dumps(dry_run, ensure_ascii=False),
                    json.dumps(impact, ensure_ascii=False),
                    row["staging_id"],
                ],
            )
    except Exception:
        plan = None

    out = dict(row)
    out["report_id"] = report_id
    out["dry_run"] = dry_run
    out["impact"] = impact
    out["payload_path"] = str(payload_path)
    out["intake_plan"] = plan
    out["plan_report_id"] = plan_report_id
    out["blocked_detail_count"] = detail_n
    return out


def _backfill_legacy_dry_run(d: dict) -> None:
    """旧版本生成的 dry_run 缺 clean_sample/clean_columns/quality（存量记录）。

    从已保存的规整 payload parquet 读回补全，避免前端「规整后预览」「质量检查」区块空白。
    仅内存补全，不写库、不改变 status/release_id。
    """
    dry = d.get("dry_run")
    if not isinstance(dry, dict):
        return
    if (
        dry.get("clean_sample") is not None
        and dry.get("clean_columns") is not None
        and dry.get("quality") is not None
    ):
        return
    if dry.get("payload_kind") != "tabular" or not dry.get("target_domain"):
        return
    payload = staging_payload_path(
        d["file_id"], dry.get("config_version") or "v1", dry["target_domain"]
    )
    if not payload.exists():
        return
    try:
        clean = pd.read_parquet(payload)
    except Exception:
        return
    if dry.get("clean_columns") is None:
        dry["clean_columns"] = [str(c) for c in clean.columns]
    if dry.get("clean_sample") is None:
        dry["clean_sample"] = _clean_sample(clean)
    if dry.get("quality") is None and dry["target_domain"] != "generic":
        try:
            from app.services.intake.quality_precheck import run_quality_precheck

            dry["quality"] = run_quality_precheck(
                clean,
                domain=dry["target_domain"],
                col_map=dry.get("column_mapping") or {},
            )
        except Exception:
            dry["quality"] = None


def get_staging(file_id: str) -> dict | None:
    with meta_tx() as con:
        row = con.execute(
            """
            SELECT * FROM staging_record
            WHERE file_id=?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            [file_id],
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["dry_run"] = json.loads(d.pop("dry_run_json") or "{}")
        d["impact"] = json.loads(d.pop("impact_json") or "{}")
    _backfill_legacy_dry_run(d)
    return d


def discard_staging(file_id: str) -> bool:
    with meta_tx() as con:
        row = con.execute(
            "SELECT staging_id, status FROM staging_record WHERE file_id=? ORDER BY updated_at DESC LIMIT 1",
            [file_id],
        ).fetchone()
        if not row:
            return False
        if row["status"] == "RELEASED":
            raise ValueError("cannot discard released staging")
        if row["status"] == "RELEASING":
            raise ValueError("cannot discard while releasing")
        con.execute("DELETE FROM staging_blocked WHERE staging_id=?", [row["staging_id"]])
        con.execute("DELETE FROM staging_record WHERE staging_id=?", [row["staging_id"]])
        con.execute("UPDATE file_batch SET status='evidence_done' WHERE file_id=?", [file_id])
    return True


def staging_payload_path(file_id: str, config_version: str, target_domain: str) -> Path:
    return config.STAGING / file_id / f"{config_version}_{target_domain}.parquet"
