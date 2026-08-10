# -*- coding: utf-8 -*-
"""Single-row correction → new release + supersede (roadmap §4.3). Never in-place UPDATE."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.repositories import acquire_writer, biz_conn, meta_tx, writer_conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def propose(
    *,
    release_id: str,
    row_key: str,
    field: str,
    value_new: str | None,
    reason: str = "",
    actor: str,
) -> dict[str, Any]:
    release_id = (release_id or "").strip()
    row_key = (row_key or "").strip()
    field = (field or "").strip()
    if not release_id or not row_key or not field:
        raise ValueError("release_id, row_key, field required")
    with meta_tx() as con:
        man = con.execute(
            "SELECT release_id FROM release_manifest WHERE release_id=?", [release_id]
        ).fetchone()
        if not man:
            raise KeyError("release not found")
    # verify row exists in biz lineage snapshot
    bcon = biz_conn()
    try:
        row = bcon.execute(
            """
            SELECT row_key, payload_json, target_domain, file_id
            FROM fact_release_rows
            WHERE source_release_id=? AND row_key=?
            """,
            [release_id, row_key],
        ).fetchone()
    finally:
        bcon.close()
    if not row:
        raise KeyError("row_key not found in release")
    cid = f"corr_{_sid(10)}"
    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO correction_request (
                correction_id, release_id, row_key, field, value_new, reason, status, actor
            ) VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?)
            """,
            [cid, release_id, row_key, field, value_new, reason, actor],
        )
    return {
        "ok": True,
        "correction_id": cid,
        "status": "proposed",
        "target_domain": row[2] if not hasattr(row, "keys") else row["target_domain"],
    }


def list_corrections(*, status: str | None = None, limit: int = 50) -> dict:
    limit = max(1, min(int(limit), 200))
    with meta_tx() as con:
        if status:
            rows = con.execute(
                """
                SELECT * FROM correction_request WHERE status=?
                ORDER BY created_at DESC LIMIT ?
                """,
                [status, limit],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM correction_request ORDER BY created_at DESC LIMIT ?",
                [limit],
            ).fetchall()
    return {"total": len(rows), "items": [dict(r) for r in rows]}


def decline(correction_id: str, *, actor: str) -> dict:
    with meta_tx() as con:
        row = con.execute(
            "SELECT * FROM correction_request WHERE correction_id=?", [correction_id]
        ).fetchone()
        if not row:
            raise KeyError("correction not found")
        if row["status"] != "proposed":
            raise RuntimeError(f"invalid status: {row['status']}")
        con.execute(
            "UPDATE correction_request SET status='declined', actor=? WHERE correction_id=?",
            [actor, correction_id],
        )
    return {"ok": True, "correction_id": correction_id, "status": "declined"}


def apply(correction_id: str, *, actor: str) -> dict[str, Any]:
    """Clone release rows with patched payload → new release + supersede older."""
    with meta_tx() as con:
        corr = con.execute(
            "SELECT * FROM correction_request WHERE correction_id=?", [correction_id]
        ).fetchone()
        if not corr:
            raise KeyError("correction not found")
        if corr["status"] != "proposed":
            raise RuntimeError(f"invalid status: {corr['status']}")
        corr = dict(corr)

    older = corr["release_id"]
    row_key = corr["row_key"]
    field = corr["field"]
    value_new = corr["value_new"]

    bcon = biz_conn()
    try:
        rows = bcon.execute(
            """
            SELECT file_id, target_domain, row_key, payload_json
            FROM fact_release_rows
            WHERE source_release_id=?
            """,
            [older],
        ).fetchall()
        man = None
    finally:
        bcon.close()
    if not rows:
        raise RuntimeError("source release has no fact_release_rows")

    with meta_tx() as con:
        man = con.execute(
            "SELECT * FROM release_manifest WHERE release_id=?", [older]
        ).fetchone()
    if not man:
        raise KeyError("release not found")
    man = dict(man)

    new_release = f"rel_corr_{_sid(10)}"
    file_id = rows[0]["file_id"] if hasattr(rows[0], "keys") else rows[0][0]
    domain = rows[0]["target_domain"] if hasattr(rows[0], "keys") else rows[0][1]
    patched = 0
    new_payloads: list[tuple[str, str, str, str]] = []
    for r in rows:
        rk = r["row_key"] if hasattr(r, "keys") else r[2]
        payload_s = r["payload_json"] if hasattr(r, "keys") else r[3]
        fid = r["file_id"] if hasattr(r, "keys") else r[0]
        td = r["target_domain"] if hasattr(r, "keys") else r[1]
        try:
            payload = json.loads(payload_s)
        except Exception:
            payload = {}
        if rk == row_key:
            # coerce numbers when obvious
            v: Any = value_new
            if value_new is not None:
                try:
                    if isinstance(payload.get(field), (int, float)) or (
                        isinstance(value_new, str)
                        and value_new.replace(".", "", 1).lstrip("-").isdigit()
                    ):
                        v = float(value_new) if "." in str(value_new) else int(float(value_new))
                except Exception:
                    v = value_new
            payload[field] = v
            patched += 1
        new_payloads.append((fid, td, rk, json.dumps(payload, ensure_ascii=False)))

    if patched != 1:
        raise RuntimeError(f"expected 1 patched row, got {patched}")

    lock = acquire_writer()
    try:
        wcon = writer_conn()
        try:
            for fid, td, rk, pj in new_payloads:
                wcon.execute(
                    """
                    INSERT INTO fact_release_rows
                      (source_release_id, file_id, target_domain, row_key, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [new_release, fid, td, rk, pj],
                )
            # domain fact table: delete-and-replace matching inventory row if present
            if domain == "inventory":
                target_payload = json.loads(
                    next(pj for _, _, rk, pj in new_payloads if rk == row_key)
                )
                inv_id = target_payload.get("inventory_id") or row_key
                existing = wcon.execute(
                    "SELECT inventory_id FROM fact_inventory WHERE inventory_id=?",
                    [inv_id],
                ).fetchone()
                if existing:
                    wcon.execute("DELETE FROM fact_inventory WHERE inventory_id=?", [inv_id])
                    cols = [
                        "inventory_id",
                        "material_id",
                        "region",
                        "category",
                        "source_file",
                        "stock_qty",
                        "quota_qty",
                        "stock_value",
                        "location",
                        "source_release_id",
                    ]
                    vals = [
                        inv_id,
                        target_payload.get("material_id"),
                        target_payload.get("region"),
                        target_payload.get("category"),
                        target_payload.get("source_file") or file_id,
                        target_payload.get("stock_qty"),
                        target_payload.get("quota_qty"),
                        target_payload.get("stock_value"),
                        target_payload.get("location"),
                        new_release,
                    ]
                    wcon.execute(
                        f"INSERT INTO fact_inventory ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
                        vals,
                    )
        finally:
            wcon.close()
    finally:
        lock.release()

    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO release_manifest (
                release_id, file_id, config_version, staging_id, clean_rows, blocked_rows,
                material_ops_json, fingerprint, released_by, status, supersedes
            ) VALUES (?, ?, ?, ?, ?, 0, ?, NULL, ?, 'released', ?)
            """,
            [
                new_release,
                man.get("file_id") or file_id,
                str(man.get("config_version") or "1"),
                man.get("staging_id") or f"corr_{correction_id}",
                len(new_payloads),
                json.dumps({"correction_id": correction_id}, ensure_ascii=False),
                actor,
                older,
            ],
        )
        con.execute(
            "UPDATE release_manifest SET superseded_by=? WHERE release_id=?",
            [new_release, older],
        )
        con.execute(
            """
            UPDATE correction_request
            SET status='applied', actor=?
            WHERE correction_id=?
            """,
            [actor, correction_id],
        )
        con.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES ('correction_apply', ?, ?, ?)
            """,
            [
                new_release,
                actor,
                json.dumps(
                    {
                        "correction_id": correction_id,
                        "supersedes": older,
                        "row_key": row_key,
                        "field": field,
                        "value_new": value_new,
                    },
                    ensure_ascii=False,
                ),
            ],
        )
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('correction', ?, 'applied', ?, ?)
            """,
            [
                json.dumps(
                    {"correction_id": correction_id, "new_release": new_release},
                    ensure_ascii=False,
                ),
                f"{field}={value_new}",
                actor,
            ],
        )

    return {
        "ok": True,
        "correction_id": correction_id,
        "status": "applied",
        "new_release_id": new_release,
        "supersedes": older,
        "patched_rows": patched,
    }
