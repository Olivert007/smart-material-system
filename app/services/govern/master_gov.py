# -*- coding: utf-8 -*-
"""Master data pending queue (docs/04 §7) — L3 → human → writer.master_apply."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.repositories import biz_conn, meta_tx


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def _norm(s: str | None) -> str:
    s = (s or "").strip().lower()
    return re.sub(r"[\s\-_/\\（）()【】\[\]·•,，.。:：;；]+", "", s)


def _ensure_table(con) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS master_pending (
            pending_id TEXT PRIMARY KEY,
            material_id TEXT,
            material_code TEXT,
            material_name TEXT,
            spec TEXT,
            unit TEXT,
            category TEXT,
            source_file TEXT,
            source_release_id TEXT,
            match_level TEXT NOT NULL DEFAULT 'L3',
            conflict_type TEXT,
            candidates_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            decided_by TEXT,
            decided_at TEXT,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(material_id)
        )
        """
    )


def _scan_l3_rows() -> list[dict[str, Any]]:
    con = biz_conn()
    try:
        rel = con.execute(
            """
            SELECT material_id, material_code, material_name, spec, unit, category,
                   source_file, source_release_id, match_level, code_source
            FROM dim_material
            WHERE COALESCE(match_level, 'L3') LIKE 'L3%'
              AND COALESCE(match_level, '') NOT IN ('L3_rejected')
              AND COALESCE(code_source, '') NOT IN (
                'master_confirm', 'human_confirm', 'approved',
                'master_reject', 'master_merge'
              )
            """
        )
        cols = [c[0] for c in rel.description]
        rows = [dict(zip(cols, r)) for r in rel.fetchall()]
    finally:
        con.close()
    return rows


def _conflict_for(row: dict[str, Any], universe: list[dict[str, Any]]) -> tuple[str | None, list[dict]]:
    code = (row.get("material_code") or "").strip()
    name_n = _norm(row.get("material_name"))
    spec_n = _norm(row.get("spec"))
    mid = row.get("material_id")
    cands: list[dict] = []
    conflict = None
    for u in universe:
        if u.get("material_id") == mid:
            continue
        ucode = (u.get("material_code") or "").strip()
        uname = _norm(u.get("material_name"))
        uspec = _norm(u.get("spec"))
        if code and ucode and code == ucode and name_n and uname and name_n != uname:
            conflict = "code_same_name_diff"
            cands.append(
                {
                    "material_id": u["material_id"],
                    "material_code": ucode,
                    "material_name": u.get("material_name"),
                    "spec": u.get("spec"),
                    "why": conflict,
                }
            )
        elif name_n and uname and name_n == uname and spec_n == uspec and code and ucode and code != ucode:
            conflict = conflict or "name_same_code_diff"
            cands.append(
                {
                    "material_id": u["material_id"],
                    "material_code": ucode,
                    "material_name": u.get("material_name"),
                    "spec": u.get("spec"),
                    "why": "name_same_code_diff",
                }
            )
        elif name_n and uname and name_n == uname and spec_n and uspec and spec_n != uspec:
            if not conflict:
                conflict = "spec_diff"
            cands.append(
                {
                    "material_id": u["material_id"],
                    "material_code": ucode,
                    "material_name": u.get("material_name"),
                    "spec": u.get("spec"),
                    "why": "spec_diff",
                }
            )
    return conflict, cands[:5]


def propose_from_dim(*, limit: int = 500) -> dict[str, Any]:
    """Enqueue L3 / unconfirmed dim rows into master_pending (meta only)."""
    rows = _scan_l3_rows()[:limit]
    universe = rows[:]  # conflict within L3 set + we'll also load all dims for compare
    con = biz_conn()
    try:
        rel = con.execute(
            "SELECT material_id, material_code, material_name, spec FROM dim_material"
        )
        cols = [c[0] for c in rel.description]
        universe = [dict(zip(cols, r)) for r in rel.fetchall()]
    finally:
        con.close()

    enqueued = 0
    refreshed = 0
    with meta_tx() as con:
        _ensure_table(con)
        for r in rows:
            mid = r.get("material_id")
            if not mid:
                continue
            conflict, cands = _conflict_for(r, universe)
            existing = con.execute(
                "SELECT pending_id, status FROM master_pending WHERE material_id=?",
                [mid],
            ).fetchone()
            payload = json.dumps(cands, ensure_ascii=False)
            if existing:
                if existing["status"] != "pending":
                    continue
                con.execute(
                    """
                    UPDATE master_pending
                    SET material_code=?, material_name=?, spec=?, unit=?, category=?,
                        source_file=?, source_release_id=?, match_level=?,
                        conflict_type=?, candidates_json=?, updated_at=datetime('now')
                    WHERE pending_id=?
                    """,
                    [
                        r.get("material_code"),
                        r.get("material_name"),
                        r.get("spec"),
                        r.get("unit"),
                        r.get("category"),
                        r.get("source_file"),
                        r.get("source_release_id"),
                        r.get("match_level") or "L3",
                        conflict,
                        payload,
                        existing["pending_id"],
                    ],
                )
                refreshed += 1
                continue
            con.execute(
                """
                INSERT INTO master_pending (
                    pending_id, material_id, material_code, material_name, spec, unit, category,
                    source_file, source_release_id, match_level, conflict_type, candidates_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                [
                    _sid(),
                    mid,
                    r.get("material_code"),
                    r.get("material_name"),
                    r.get("spec"),
                    r.get("unit"),
                    r.get("category"),
                    r.get("source_file"),
                    r.get("source_release_id"),
                    r.get("match_level") or "L3",
                    conflict,
                    payload,
                ],
            )
            enqueued += 1
    return {
        "ok": True,
        "scanned": len(rows),
        "enqueued": enqueued,
        "refreshed": refreshed,
        "hint": "L3/未确认主数据已入 master_pending；审批后经 writer.master_apply 写 DuckDB",
    }


def list_pending(
    *,
    status: str = "pending",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    with meta_tx() as con:
        _ensure_table(con)
        total = con.execute(
            "SELECT COUNT(*) AS c FROM master_pending WHERE status=?", [status]
        ).fetchone()["c"]
        rows = con.execute(
            """
            SELECT * FROM master_pending
            WHERE status=?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            [status, limit, offset],
        ).fetchall()
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
        items.append(d)
    return {"total": total, "items": items, "limit": limit, "offset": offset}


def confirm_pending(
    *,
    pending_id: str,
    decision: str,
    actor: str,
    note: str = "",
    merge_to_material_id: str | None = None,
    material_patch: dict | None = None,
) -> dict[str, Any]:
    """approve | reject | merge — biz write only via writer."""
    decision = (decision or "").strip().lower()
    if decision not in ("approve", "reject", "merge"):
        raise ValueError("decision must be approve|reject|merge")

    patch_keys = ("material_code", "material_name", "spec", "unit", "category")
    patch: dict[str, Any] = {}
    if material_patch:
        for k in patch_keys:
            if k in material_patch and material_patch[k] is not None:
                patch[k] = str(material_patch[k]).strip()
        if patch and not (patch.get("material_name") or patch.get("material_code")):
            raise ValueError("修正时至少填写物资名称或物资编码")

    with meta_tx() as con:
        _ensure_table(con)
        row = con.execute(
            "SELECT * FROM master_pending WHERE pending_id=?", [pending_id]
        ).fetchone()
        if not row:
            raise KeyError("pending not found")
        if row["status"] != "pending":
            raise RuntimeError(f"invalid status: {row['status']}")
        drow = dict(row)
        if patch and decision == "approve":
            drow.update(patch)

    applied = None
    new_status = "rejected"
    if decision == "approve":
        from app.services.writer import master_apply

        applied = master_apply(
            materials=[
                {
                    "material_id": drow.get("material_id"),
                    "material_code": drow.get("material_code"),
                    "material_name": drow.get("material_name"),
                    "spec": drow.get("spec"),
                    "unit": drow.get("unit"),
                    "category": drow.get("category"),
                    "source_file": drow.get("source_file"),
                    "source_release_id": drow.get("source_release_id"),
                }
            ],
            actor=actor,
            action="approve",
        )
        new_status = "approved"
    elif decision == "merge":
        target = (merge_to_material_id or "").strip()
        if not target:
            # pick first candidate if any
            try:
                cands = json.loads(drow.get("candidates_json") or "[]")
            except json.JSONDecodeError:
                cands = []
            if cands:
                target = str(cands[0].get("material_id") or "")
        if not target:
            raise ValueError("merge requires merge_to_material_id or candidates")
        from app.services.writer import apply_material_align, master_apply

        # mark merge mapping + remap flows
        applied = apply_material_align(
            pairs=[(str(drow.get("material_id")), target)], actor=actor
        )
        master_apply(
            materials=[{"material_id": drow.get("material_id"), "merge_to": target}],
            actor=actor,
            action="merge",
        )
        new_status = "merged"
    else:
        from app.services.writer import master_apply

        applied = master_apply(
            materials=[{"material_id": drow.get("material_id")}],
            actor=actor,
            action="reject",
        )
        new_status = "rejected"

    with meta_tx() as con:
        con.execute(
            """
            UPDATE master_pending
            SET status=?, decided_by=?, decided_at=datetime('now'), note=?,
                version=version+1, updated_at=datetime('now')
            WHERE pending_id=?
            """,
            [new_status, actor, (note or "")[:200], pending_id],
        )
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('master_pending', ?, ?, ?, ?)
            """,
            [
                json.dumps(
                    {
                        "pending_id": pending_id,
                        "material_id": drow.get("material_id"),
                        "decision": decision,
                        "merge_to": merge_to_material_id,
                    },
                    ensure_ascii=False,
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
        "status": new_status,
        "applied": applied,
        "actor": actor,
        "mutates_biz": decision in ("approve", "merge"),
    }
