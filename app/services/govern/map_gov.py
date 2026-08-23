# -*- coding: utf-8 -*-
"""Step2 map governance queue (docs/03 Step2 / 04 §6.4).

Low-confidence / multi-candidate / dict-conflict headers enter map_pending.
Human confirm writes rule_dict; never auto-publish to DuckDB.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pandas as pd

from app.repositories import meta_tx
from app.services.govern.mapping_suggest import classify_queue_items, suggest_header_mapping


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def enqueue_headers(
    headers: list[str],
    *,
    file_id: str | None = None,
    sheet: str | None = None,
    business_domain: str = "default",
    suggest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Suggest (if needed) and upsert uncertain headers into map_pending."""
    headers = [str(h).strip() for h in headers if str(h).strip()]
    if not headers:
        return {"ok": False, "error": "empty headers", "enqueued": 0, "items": []}

    sug = suggest or suggest_header_mapping(headers, business_domain=business_domain)
    items = classify_queue_items(headers, sug)
    fid = file_id or ""
    sh = sheet or ""
    enqueued = 0
    pending_ids: list[str] = []

    with meta_tx() as con:
        for it in items:
            pid = _sid()
            existing = con.execute(
                """
                SELECT pending_id, status FROM map_pending
                WHERE COALESCE(file_id,'')=? AND COALESCE(sheet,'')=? AND header=? AND business_domain=?
                """,
                [fid, sh, it["header"], business_domain],
            ).fetchone()
            if existing and existing["status"] == "pending":
                con.execute(
                    """
                    UPDATE map_pending
                    SET suggested_field=?, candidates_json=?, reason=?, updated_at=datetime('now')
                    WHERE pending_id=?
                    """,
                    [
                        it.get("suggested_field"),
                        json.dumps(it.get("candidates") or [], ensure_ascii=False),
                        it["reason"],
                        existing["pending_id"],
                    ],
                )
                pending_ids.append(existing["pending_id"])
                enqueued += 1
                continue
            if existing and existing["status"] in ("accepted", "ignored"):
                # re-open for new suggest pass
                con.execute(
                    """
                    UPDATE map_pending
                    SET status='pending', suggested_field=?, candidates_json=?, reason=?,
                        actor=NULL, note=NULL, updated_at=datetime('now')
                    WHERE pending_id=?
                    """,
                    [
                        it.get("suggested_field"),
                        json.dumps(it.get("candidates") or [], ensure_ascii=False),
                        it["reason"],
                        existing["pending_id"],
                    ],
                )
                pending_ids.append(existing["pending_id"])
                enqueued += 1
                continue

            con.execute(
                """
                INSERT INTO map_pending (
                    pending_id, file_id, sheet, header, suggested_field, candidates_json,
                    reason, status, business_domain
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                [
                    pid,
                    fid,
                    sh,
                    it["header"],
                    it.get("suggested_field"),
                    json.dumps(it.get("candidates") or [], ensure_ascii=False),
                    it["reason"],
                    business_domain,
                ],
            )
            pending_ids.append(pid)
            enqueued += 1

    return {
        "ok": True,
        "enqueued": enqueued,
        "pending_ids": pending_ids,
        "items": items,
        "skipped_high_confidence": len(headers) - len(items),
        "suggest_state": sug.get("model_state"),
        "mapping_preview": sug.get("mapping"),
        "hint": "多候选/低置信/冲突已入 map_pending；须人工确认后回写 rule_dict，不可静默入库",
    }


def list_pending(
    *,
    status: str = "pending",
    limit: int = 50,
    offset: int = 0,
    file_id: str | None = None,
) -> dict[str, Any]:
    with meta_tx() as con:
        where = ["status=?"]
        args: list[Any] = [status]
        if file_id:
            where.append("file_id=?")
            args.append(file_id)
        wh = " AND ".join(where)
        total = con.execute(
            f"SELECT COUNT(*) AS c FROM map_pending WHERE {wh}", args
        ).fetchone()["c"]
        rows = con.execute(
            f"""
            SELECT pending_id, file_id, sheet, header, suggested_field, candidates_json,
                   reason, status, business_domain, actor, note, created_at, updated_at
            FROM map_pending
            WHERE {wh}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*args, limit, offset],
        ).fetchall()
        file_names: dict[str, str] = {}
        try:
            for fr in con.execute("SELECT file_id, filename FROM file_batch").fetchall():
                fid = str(fr["file_id"] or "").strip()
                if fid:
                    file_names[fid] = str(fr["filename"] or "").strip() or fid
        except Exception:
            file_names = {}
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["candidates"] = json.loads(d.pop("candidates_json") or "[]")
        except json.JSONDecodeError:
            d["candidates"] = []
            d.pop("candidates_json", None)
        else:
            d.pop("candidates_json", None)
        fid = str(d.get("file_id") or "").strip()
        d["source_file"] = file_names.get(fid) or fid or None
        items.append(d)
    return {"total": total, "items": items, "limit": limit, "offset": offset}


def confirm_pending(
    *,
    pending_id: str,
    decision: str,
    std_field: str | None = None,
    note: str = "",
    actor: str = "ops",
) -> dict[str, Any]:
    """accept|amend → rule_dict; ignore → status only (optional ignore rule)."""
    decision = (decision or "").strip().lower()
    if decision not in ("accept", "amend", "ignore"):
        raise ValueError("decision must be accept|amend|ignore")

    # schema 兜底在事务外执行，避免提前 commit 破坏 meta_tx 原子性
    from app.services.govern.rule_dict import ensure_rule_dict_schema

    ensure_rule_dict_schema()

    with meta_tx() as con:
        row = con.execute(
            "SELECT * FROM map_pending WHERE pending_id=?", [pending_id]
        ).fetchone()
        if not row:
            raise KeyError("pending not found")
        if row["status"] != "pending":
            raise RuntimeError(f"invalid status: {row['status']}")

        field = (std_field or row["suggested_field"] or "ignore").strip()
        if decision == "ignore":
            field = "ignore"
        if decision == "amend" and not std_field:
            raise ValueError("amend requires std_field")

        if decision in ("accept", "amend") or (decision == "ignore"):
            # ignore also records ignore mapping so resolve_columns skips the header
            con.execute(
                """
                INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
                VALUES (?, ?, ?, 1, 'map_pending_confirm', ?)
                ON CONFLICT(header, business_domain, std_field) DO UPDATE SET
                    hits = hits + 1,
                    confirmed_by = excluded.confirmed_by,
                    source = excluded.source
                """,
                [row["header"][:120], field[:64], (row["business_domain"] or "default")[:64], actor],
            )

        new_status = "ignored" if decision == "ignore" else "accepted"
        con.execute(
            """
            UPDATE map_pending
            SET status=?, suggested_field=?, actor=?, note=?,
                version=version+1, updated_at=datetime('now')
            WHERE pending_id=?
            """,
            [new_status, field, actor, (note or "")[:200], pending_id],
        )
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('map_pending', ?, ?, ?, ?)
            """,
            [
                _dumps(
                    {
                        "pending_id": pending_id,
                        "header": row["header"],
                        "std_field": field,
                        "reason": row["reason"],
                    }
                )[:200],
                decision,
                (note or "")[:200],
                actor,
            ],
        )

    return {
        "ok": True,
        "pending_id": pending_id,
        "decision": decision,
        "std_field": field,
        "status": new_status,
        "actor": actor,
    }


def headers_from_evidence_sheet(
    evidence: pd.DataFrame,
    sheet: str,
    header_row: int,
) -> list[str]:
    sub = evidence.loc[
        (evidence["sheet"].astype(str) == str(sheet))
        & (pd.to_numeric(evidence["row"], errors="coerce") == int(header_row))
    ]
    if sub.empty:
        return []
    # sort by column letter roughly
    def _col_key(c: str) -> tuple:
        s = str(c)
        return (len(s), s)

    sub = sub.copy()
    sub["_ck"] = sub["col"].map(_col_key)
    sub = sub.sort_values("_ck")
    headers: list[str] = []
    for v in sub["raw_value"].tolist():
        h = str(v).strip()
        if h and h.lower() not in {"nan", "none"}:
            headers.append(h)
    return headers


def enqueue_from_file(
    file_id: str,
    *,
    business_domain: str = "default",
    only_roles: tuple[str, ...] = ("detail", "unknown", "wide_export"),
) -> dict[str, Any]:
    """Use Step1 profile + evidence to enqueue uncertain headers per sheet."""
    from app.services.intake.evidence import evidence_path
    from app.services.intake.profile import get_workbook_profile, profile_file_evidence

    path = evidence_path(file_id)
    if not path.exists():
        raise FileNotFoundError(f"evidence missing: {file_id}")

    prof = get_workbook_profile(file_id)
    if not prof:
        profile_file_evidence(file_id)
        prof = get_workbook_profile(file_id)
    sheets = (prof or {}).get("profile", {}).get("sheets") or []
    evidence = pd.read_parquet(path)

    results = []
    total = 0
    for sp in sheets:
        role = sp.get("role_hint")
        if only_roles and role not in only_roles:
            continue
        cands = sp.get("header_row_candidates") or []
        if not cands:
            continue
        headers = headers_from_evidence_sheet(evidence, sp["sheet"], int(cands[0]))
        if not headers:
            continue
        out = enqueue_headers(
            headers,
            file_id=file_id,
            sheet=sp["sheet"],
            business_domain=business_domain,
        )
        total += int(out.get("enqueued") or 0)
        results.append(
            {
                "sheet": sp["sheet"],
                "role_hint": role,
                "headers": headers,
                "enqueued": out.get("enqueued"),
                "items": out.get("items"),
            }
        )

    return {
        "ok": True,
        "file_id": file_id,
        "enqueued": total,
        "sheets": results,
        "hint": "仅 detail/unknown/wide_export sheet 入队；确认前不写业务库",
    }
