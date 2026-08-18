# -*- coding: utf-8 -*-
"""Staging quality aggregates + blocked listing (roadmap §2 / P1-2)."""
from __future__ import annotations

import uuid
from typing import Any

from app.repositories import meta_tx


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def replace_blocked_details(
    *,
    staging_id: str,
    file_id: str,
    target_domain: str,
    details: list[dict[str, Any]],
) -> int:
    """Delete+insert blocked details for a staging_id (same meta txn caller)."""
    with meta_tx() as con:
        con.execute("DELETE FROM staging_blocked WHERE staging_id=?", [staging_id])
        n = 0
        for d in details:
            con.execute(
                """
                INSERT INTO staging_blocked (
                    block_id, staging_id, file_id, target_domain,
                    source_row, header, reason_code, reason_detail, raw_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    _sid(),
                    staging_id,
                    file_id,
                    target_domain,
                    d.get("source_row"),
                    (d.get("header") or "")[:120],
                    d.get("reason_code") or "OTHER",
                    (d.get("reason_detail") or "")[:200],
                    (d.get("raw_value") or "")[:200] if d.get("raw_value") is not None else None,
                ],
            )
            n += 1
    return n


def quality_report(file_id: str) -> dict[str, Any]:
    with meta_tx() as con:
        st = con.execute(
            """
            SELECT * FROM staging_record
            WHERE file_id=?
            ORDER BY updated_at DESC, rowid DESC LIMIT 1
            """,
            [file_id],
        ).fetchone()
        if not st:
            raise KeyError("staging not found")
        sid = st["staging_id"]
        clean = int(st["clean_rows"] or 0)
        blocked = int(st["blocked_rows"] or 0)
        total = clean + blocked
        by_code = con.execute(
            """
            SELECT reason_code, COUNT(*) AS c
            FROM staging_blocked WHERE staging_id=?
            GROUP BY reason_code ORDER BY c DESC
            """,
            [sid],
        ).fetchall()
        by_header = con.execute(
            """
            SELECT COALESCE(header,'(none)') AS header, COUNT(*) AS c
            FROM staging_blocked WHERE staging_id=?
            GROUP BY header ORDER BY c DESC LIMIT 10
            """,
            [sid],
        ).fetchall()
        detail_n = con.execute(
            "SELECT COUNT(*) AS c FROM staging_blocked WHERE staging_id=?", [sid]
        ).fetchone()["c"]
    return {
        "file_id": file_id,
        "staging_id": sid,
        "status": st["status"],
        "target_domain": st["target_domain"],
        "clean_rows": clean,
        "blocked_rows": blocked,
        "total_rows": total,
        "block_rate": (blocked / total) if total else 0.0,
        "clean_rate": (clean / total) if total else 0.0,
        "detail_count": detail_n,
        "by_reason_code": {r["reason_code"]: r["c"] for r in by_code},
        "by_header_top10": [{"header": r["header"], "count": r["c"]} for r in by_header],
    }


def quality_report_by_release(release_id: str) -> dict[str, Any]:
    with meta_tx() as con:
        man = con.execute(
            "SELECT * FROM release_manifest WHERE release_id=?", [release_id]
        ).fetchone()
        if not man:
            raise KeyError("release not found")
        fid = man["file_id"]
    out = quality_report(fid)
    out["release_id"] = release_id
    return out


def list_blocked(
    file_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    staging_id: str | None = None,
    target_domain: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    with meta_tx() as con:
        if not staging_id:
            if target_domain:
                st = con.execute(
                    """
                    SELECT staging_id FROM staging_record
                    WHERE file_id=? AND target_domain=?
                    ORDER BY updated_at DESC, rowid DESC LIMIT 1
                    """,
                    [file_id, target_domain],
                ).fetchone()
            else:
                st = con.execute(
                    """
                    SELECT staging_id FROM staging_record
                    WHERE file_id=? ORDER BY updated_at DESC, rowid DESC LIMIT 1
                    """,
                    [file_id],
                ).fetchone()
            if not st:
                raise KeyError("staging not found")
            staging_id = st["staging_id"]
        total = con.execute(
            "SELECT COUNT(*) AS c FROM staging_blocked WHERE staging_id=?",
            [staging_id],
        ).fetchone()["c"]
        rows = con.execute(
            """
            SELECT * FROM staging_blocked
            WHERE staging_id=?
            ORDER BY source_row ASC, created_at ASC
            LIMIT ? OFFSET ?
            """,
            [staging_id, limit, offset],
        ).fetchall()
    return {
        "file_id": file_id,
        "staging_id": staging_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }
