# -*- coding: utf-8 -*-
"""Stock-flow audit + lineage rebuild (docs/12 FL7 / A6).

Never UPDATE quantity in place — revoke by source_release_id then regenerate.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.repositories import acquire_writer, biz_conn, meta_tx, writer_conn
from app.services.mapping import build_stock_flow_bundle
from app.services.staging import staging_payload_path
from app.services.writer import _upsert_materials_impl as upsert_materials


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _looks_like_year_qty(quantity: float | None, remark: str | None, unit: str | None) -> bool:
    if quantity is None:
        return False
    try:
        q = float(quantity)
    except (TypeError, ValueError):
        return False
    if q != int(q):
        return False
    yi = int(q)
    if yi < 1900 or yi > 2100:
        return False
    # Explicit unit like 个/台 after a real qty is OK even if 2000 pieces — rare.
    # Year-as-qty usually has empty unit AND remark is date-ish / year-only.
    u = (unit or "").strip()
    r = (remark or "").strip()
    if u and u not in {"年", "年份"}:
        # still suspicious if remark is pure year/date and qty equals that year
        m = re.search(r"((?:19|20)\d{2})", r)
        if m and int(m.group(1)) == yi and not re.search(r"(入|出|领|借|库).{0,6}" + str(yi), r):
            return True
        return False
    # empty unit + year range → treat as bad
    if re.fullmatch(r"(?:19|20)\d{2}年?(?:之前|以前)?(?:采购|购入)?", re.sub(r"\s+", "", r) or ""):
        return True
    if re.match(r"^(?:19|20)\d{2}([-./年])", r) and not re.search(rf"(入|出|领用|借用).{{0,8}}{yi}", r):
        return True
    if not r:
        return True
    return True


def audit_stock_flow(*, limit: int = 5000) -> dict[str, Any]:
    """Return suspicious fact_stock_flow rows (year-as-qty etc.)."""
    con = biz_conn()
    try:
        # Ensure table exists / readable
        try:
            df = con.execute(
                """
                SELECT flow_id, material_id, flow_type, flow_date, quantity, unit,
                       person, purpose, remark, parse_level, parse_source,
                       source_file, source_sheet, source_row, source_segment,
                       source_release_id
                FROM fact_stock_flow
                """
            ).fetchdf()
        except Exception as e:
            return {"ok": False, "error": str(e), "suspicious": [], "by_release": {}}
    finally:
        con.close()

    suspicious: list[dict] = []
    for _, row in df.iterrows():
        qty = row.get("quantity")
        reasons: list[str] = []
        if _looks_like_year_qty(
            float(qty) if qty is not None and qty == qty else None,
            None if pd.isna(row.get("remark")) else str(row.get("remark")),
            None if pd.isna(row.get("unit")) else str(row.get("unit")),
        ):
            reasons.append("year_as_quantity")
        # missing parse_level on published rows (legacy)
        pl = row.get("parse_level")
        if pl is None or (isinstance(pl, float) and pd.isna(pl)) or str(pl).strip() == "":
            reasons.append("missing_parse_level")
        if not reasons:
            continue
        item = {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in row.to_dict().items()}
        item["reasons"] = reasons
        suspicious.append(item)
        if len(suspicious) >= limit:
            break

    by_release: dict[str, int] = {}
    for s in suspicious:
        rid = s.get("source_release_id") or ""
        by_release[rid] = by_release.get(rid, 0) + 1

    return {
        "ok": True,
        "total_rows": int(len(df)),
        "suspicious_count": len(suspicious),
        "by_release": by_release,
        "suspicious": suspicious,
    }


def revoke_stock_flow_release(release_id: str, *, actor: str) -> dict:
    """Delete derived stock_flow (+ materials tagged by this release). No in-place UPDATE."""
    if not release_id:
        raise ValueError("release_id required")
    lock = acquire_writer()
    deleted = 0
    try:
        con = writer_conn()
        try:
            before = con.execute(
                "SELECT COUNT(*) FROM fact_stock_flow WHERE source_release_id = ?",
                [release_id],
            ).fetchone()[0]
            con.execute("DELETE FROM fact_stock_flow WHERE source_release_id = ?", [release_id])
            con.execute(
                """
                DELETE FROM fact_release_rows
                WHERE source_release_id = ? AND target_domain = 'stock_flow'
                """,
                [release_id],
            )
            con.execute("DELETE FROM dim_material WHERE source_release_id = ?", [release_id])
            deleted = int(before)
        finally:
            con.close()
        with meta_tx() as mcon:
            mcon.execute(
                """
                INSERT INTO write_audit (action, release_id, actor, detail_json)
                VALUES ('lineage_revoke_stock_flow', ?, ?, ?)
                """,
                [
                    release_id,
                    actor,
                    json.dumps({"deleted_flows": deleted}, ensure_ascii=False),
                ],
            )
    finally:
        lock.release()
    return {"ok": True, "release_id": release_id, "deleted_flows": deleted}


def rebuild_stock_flow_release(release_id: str, *, actor: str) -> dict:
    """Revoke then regenerate fact_stock_flow from staging parquet (FL7)."""
    if not release_id:
        raise ValueError("release_id required")

    with meta_tx() as con:
        staging = con.execute(
            """
            SELECT * FROM staging_record
            WHERE release_id=? AND target_domain='stock_flow'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            [release_id],
        ).fetchone()
        if not staging:
            # fallback: any staging with this release_id
            staging = con.execute(
                "SELECT * FROM staging_record WHERE release_id=? ORDER BY updated_at DESC LIMIT 1",
                [release_id],
            ).fetchone()
        if not staging:
            raise KeyError(f"staging not found for release_id={release_id}")
        staging = dict(staging)
        fb = con.execute(
            "SELECT filename FROM file_batch WHERE file_id=?", [staging["file_id"]]
        ).fetchone()
        source_file = fb["filename"] if fb else staging["file_id"]

    if staging.get("target_domain") != "stock_flow":
        raise RuntimeError(
            f"release {release_id} target_domain={staging.get('target_domain')} "
            "is not stock_flow; refuse rebuild"
        )

    path = staging_payload_path(
        staging["file_id"], staging["config_version"], staging["target_domain"]
    )
    if not path.exists():
        raise FileNotFoundError(f"staging payload missing: {path}")

    df = pd.read_parquet(path)
    from app.services.flow_example_snapshot import load_for_release

    examples = load_for_release(release_id)
    snapshot_used = examples is not None
    table, rows, pending, stats = build_stock_flow_bundle(
        df,
        file_id=staging["file_id"],
        release_id=release_id,
        source_file=source_file,
        examples=examples,
    )
    assert table == "fact_stock_flow"

    # revoke then insert (delete-and-replace)
    revoke = revoke_stock_flow_release(release_id, actor=actor)

    lock = acquire_writer()
    inserted = 0
    lineage_n = 0
    material_inserted = 0
    try:
        con = writer_conn()
        try:
            material_inserted = upsert_materials(con, rows, release_id, source_file)
            cols = [
                "flow_id", "material_id", "flow_type", "flow_date", "quantity", "unit",
                "person", "purpose", "remark", "parse_level", "parse_source",
                "source_file", "source_sheet", "source_row", "source_segment",
                "source_release_id",
            ]
            placeholders = ", ".join(["?"] * len(cols))
            col_sql = ", ".join(cols)
            lineage_n = 0
            for rec in rows:
                name = rec.pop("_material_name", None)
                code = rec.pop("_material_code", None)
                rec.pop("_spec", None)
                row_key = rec.pop("_row_key", None)
                values = [rec.get(c) for c in cols]
                con.execute(
                    f"INSERT INTO fact_stock_flow ({col_sql}) VALUES ({placeholders})",
                    values,
                )
                inserted += 1
                if not row_key:
                    row_key = (
                        f"{rec.get('source_file')}|{rec.get('source_sheet')}|"
                        f"{rec.get('source_row')}|{rec.get('source_segment')}|"
                        f"{rec.get('flow_type')}"
                    )
                payload = {
                    "flow_id": rec.get("flow_id"),
                    "material_id": rec.get("material_id"),
                    "material_name": name,
                    "material_code": code,
                    "flow_type": rec.get("flow_type"),
                    "flow_date": rec.get("flow_date"),
                    "quantity": rec.get("quantity"),
                    "source_file": rec.get("source_file"),
                    "source_sheet": rec.get("source_sheet"),
                    "source_row": rec.get("source_row"),
                    "source_segment": rec.get("source_segment"),
                    "parse_level": rec.get("parse_level"),
                }
                con.execute(
                    """
                    INSERT INTO fact_release_rows
                    (source_release_id, file_id, target_domain, row_key, payload_json)
                    VALUES (?, ?, 'stock_flow', ?, ?)
                    """,
                    [
                        release_id,
                        staging["file_id"],
                        row_key,
                        json.dumps(payload, ensure_ascii=False, default=str),
                    ],
                )
                lineage_n += 1
            con.execute(
                """
                INSERT OR REPLACE INTO write_checkpoint (release_id, row_count, target_table, updated_at)
                VALUES (?, ?, 'fact_stock_flow', current_timestamp)
                """,
                [release_id, inserted],
            )
        finally:
            con.close()
    finally:
        lock.release()

    # refresh pending for file
    with meta_tx() as con:
        con.execute(
            "DELETE FROM flow_pending WHERE file_id=? AND status='pending'",
            [staging["file_id"]],
        )
        for p in pending:
            pid = uuid.uuid4().hex[:12]
            con.execute(
                """
                INSERT INTO flow_pending (
                    pending_id, file_id, source_sheet, source_row, source_segment,
                    flow_type, text_raw, text_norm, parse_level, suggested_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                [
                    pid,
                    staging["file_id"],
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
        con.execute(
            """
            UPDATE release_manifest
            SET clean_rows=?, material_ops_json=?, released_at=datetime('now'), status='released'
            WHERE release_id=?
            """,
            [
                inserted,
                json.dumps(
                    {
                        "fact_inserted": inserted,
                        "material_inserted": material_inserted,
                        "lineage_rows": lineage_n,
                        "rebuilt": True,
                        "flow_stats": stats,
                        "example_snapshot_used": snapshot_used,
                    },
                    ensure_ascii=False,
                ),
                release_id,
            ],
        )
        con.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES ('lineage_rebuild_stock_flow', ?, ?, ?)
            """,
            [
                release_id,
                actor,
                json.dumps(
                    {
                        "deleted": revoke.get("deleted_flows"),
                        "inserted": inserted,
                        "stats": stats,
                        "pending": len(pending),
                        "example_snapshot_used": snapshot_used,
                    },
                    ensure_ascii=False,
                ),
            ],
        )

    post = audit_stock_flow(limit=1000)
    still_bad = [
        s
        for s in post.get("suspicious", [])
        if s.get("source_release_id") == release_id and "year_as_quantity" in (s.get("reasons") or [])
    ]
    return {
        "ok": True,
        "release_id": release_id,
        "deleted_flows": revoke.get("deleted_flows"),
        "inserted": inserted,
        "pending": len(pending),
        "stats": stats,
        "example_snapshot_used": snapshot_used,
        "post_audit_year_qty": len(still_bad),
        "clean_of_year_qty": len(still_bad) == 0,
    }
