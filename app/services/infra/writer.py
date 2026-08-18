# -*- coding: utf-8 -*-
"""Unique writer: idempotent intake_release into star-schema tables (D2 / 03 §4.7)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pandas as pd

from app.repositories import acquire_writer, meta_tx, writer_conn
from app.services.mapping import build_domain_rows
from app.services.staging import staging_payload_path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _rid() -> str:
    return f"rel_{uuid.uuid4().hex[:12]}"


def compensate_releasing() -> list[str]:
    done: list[str] = []
    with meta_tx() as con:
        rows = con.execute("SELECT * FROM staging_record WHERE status='RELEASING'").fetchall()
    for row in rows:
        staging = dict(row)
        release_id = staging.get("release_id") or _rid()
        try:
            _write_release(staging, release_id=release_id, actor="system:compensate")
            done.append(release_id)
        except Exception as e:
            with meta_tx() as con:
                con.execute(
                    """
                    UPDATE staging_record
                    SET status='FAILED', updated_at=?
                    WHERE staging_id=?
                    """,
                    [_now(), staging["staging_id"]],
                )
                con.execute(
                    """
                    INSERT INTO write_audit (action, release_id, actor, detail_json)
                    VALUES ('release_failed', ?, 'system:compensate', ?)
                    """,
                    [release_id, json.dumps({"error": str(e)}, ensure_ascii=False)],
                )
    return done


def confirm_release(
    *,
    file_id: str,
    actor: str,
    expected_version: int | None = None,
    expected_status: str | None = None,
    staging_id: str | None = None,
    target_domain: str | None = None,
    force: bool = False,
    supersedes: str | None = None,
) -> dict:
    from app.services.intake_plan import assert_release_gate

    try:
        assert_release_gate(file_id, force=force)
    except RuntimeError as e:
        raise RuntimeError(str(e)) from e

    with meta_tx() as con:
        row = None
        if staging_id:
            row = con.execute(
                "SELECT * FROM staging_record WHERE staging_id=?",
                [staging_id],
            ).fetchone()
            if row and str(row["file_id"]) != str(file_id):
                raise RuntimeError("STAGING_FILE_MISMATCH")
        elif target_domain:
            row = con.execute(
                """
                SELECT * FROM staging_record
                WHERE file_id=? AND target_domain=?
                ORDER BY updated_at DESC, rowid DESC
                LIMIT 1
                """,
                [file_id, target_domain],
            ).fetchone()
        else:
            row = con.execute(
                """
                SELECT * FROM staging_record
                WHERE file_id=?
                ORDER BY updated_at DESC, rowid DESC
                LIMIT 1
                """,
                [file_id],
            ).fetchone()
        if not row:
            raise KeyError("staging not found")
        staging = dict(row)
        if expected_version is not None and int(staging["version"]) != int(expected_version):
            raise RuntimeError("STAGE_VERSION_CONFLICT")
        if staging["status"] == "RELEASED":
            man = con.execute(
                "SELECT * FROM release_manifest WHERE release_id=?",
                [staging["release_id"]],
            ).fetchone()
            return {"status": "RELEASED", "release": dict(man) if man else staging, "idempotent": True}
        if expected_status is not None and staging["status"] != expected_status:
            raise RuntimeError("STAGE_STATUS_CONFLICT")
        if staging["status"] not in ("STAGED", "FAILED"):
            raise RuntimeError(f"invalid status for confirm: {staging['status']}")

        release_id = staging.get("release_id") or _rid()
        cur = con.execute(
            """
            UPDATE staging_record
            SET status='RELEASING', release_id=?, updated_at=?
            WHERE staging_id=? AND status IN ('STAGED', 'FAILED')
            """,
            [release_id, _now(), staging["staging_id"]],
        )
        if cur.rowcount != 1:
            raise RuntimeError("STAGE_CAS_CONFLICT")
        staging["release_id"] = release_id
        staging["status"] = "RELEASING"
        staging["_supersedes"] = (supersedes or "").strip() or None

    result = _write_release(staging, release_id=staging["release_id"], actor=actor)
    older = staging.get("_supersedes")
    if older:
        with meta_tx() as con:
            con.execute(
                "UPDATE release_manifest SET supersedes=? WHERE release_id=?",
                [older, staging["release_id"]],
            )
            con.execute(
                "UPDATE release_manifest SET superseded_by=? WHERE release_id=?",
                [staging["release_id"], older],
            )
        result["supersedes"] = older
    return result


def _upsert_materials_impl(con, rows: list[dict], release_id: str, source_file: str) -> int:
    n = 0
    for r in rows:
        mid = r.get("material_id")
        if not mid:
            continue
        name = r.pop("_material_name", "") or ""
        code = r.pop("_material_code", "") or ""
        spec = r.pop("_spec", "") or ""
        existing = con.execute(
            "SELECT material_id FROM dim_material WHERE material_id = ?", [mid]
        ).fetchone()
        if existing:
            continue
        con.execute(
            """
            INSERT INTO dim_material (
                material_id, material_code, material_name, spec, unit, category,
                name_alias, spec_alias, source_file, code_source, match_level, source_release_id
            ) VALUES (?, ?, ?, ?, '', '', '', '', ?, '', 'L3', ?)
            """,
            [mid, code, name, spec, source_file, release_id],
        )
        n += 1
    return n


def _write_release(
    staging: dict,
    *,
    release_id: str,
    actor: str,
    audit_action: str = "intake_release",
) -> dict:
    lock = acquire_writer()
    inserted = 0
    target_table = "fact_release_rows"
    material_ops = {"material_inserted": 0, "fact_inserted": 0}
    example_snapshot = None
    try:
        path = staging_payload_path(
            staging["file_id"], staging["config_version"], staging["target_domain"]
        )
        if not path.exists():
            raise FileNotFoundError(f"staging payload missing: {path}")
        df = pd.read_parquet(path)
        domain = staging["target_domain"]
        source_file = staging["file_id"]

        with meta_tx() as mcon:
            fb = mcon.execute(
                "SELECT filename FROM file_batch WHERE file_id=?", [staging["file_id"]]
            ).fetchone()
            if fb:
                source_file = fb["filename"]

        examples = None
        if domain == "stock_flow":
            from app.services.flow_example_snapshot import capture_for_release, snapshot_path

            examples = capture_for_release(release_id, file_id=staging["file_id"])
            example_snapshot = str(snapshot_path(release_id))

        table, mapped = build_domain_rows(
            df,
            domain=domain,
            file_id=staging["file_id"],
            release_id=release_id,
            source_file=source_file,
            examples=examples,
        )
        target_table = table

        con = writer_conn()
        try:
            # delete-and-replace by release_id (idempotent)
            if table == "fact_release_rows":
                con.execute("DELETE FROM fact_release_rows WHERE source_release_id = ?", [release_id])
                for i, rec in enumerate(mapped):
                    payload = rec.pop("_payload", {})
                    con.execute(
                        """
                        INSERT INTO fact_release_rows
                        (source_release_id, file_id, target_domain, row_key, payload_json)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        [
                            release_id,
                            staging["file_id"],
                            domain,
                            rec.get("row_key", f"r{i}"),
                            json.dumps(payload, ensure_ascii=False, default=str),
                        ],
                    )
                    inserted += 1
            else:
                con.execute(f"DELETE FROM {table} WHERE source_release_id = ?", [release_id])
                # also remove materials created solely by this release on replay
                con.execute(
                    "DELETE FROM dim_material WHERE source_release_id = ?", [release_id]
                )
                material_ops["material_inserted"] = _upsert_materials_impl(
                    con, mapped, release_id, source_file
                )
                cols_by_table = {
                    "fact_inventory": [
                        "inventory_id", "material_id", "row_key", "region", "category", "source_file",
                        "source_era", "color_flag", "stock_qty", "opening_qty", "quota_qty",
                        "min_qty", "temp_qty", "company_wh_qty", "age_days", "unit_cost",
                        "stock_value", "unit", "location", "custodian",
                        # T1: ledger-export-plan §7.1 (LD-1 锁定 2026-08-10)
                        "remark", "belong_system", "project_name", "consumption_plan",
                        "material_source", "group_code", "is_frame_material",
                        "agreement_supplier", "frame_material_code", "frame_material_name",
                        "frame_material_spec", "frame_material_supplier", "emergency_supplier",
                        "source_sheet", "source_release_id",
                    ],
                    "fact_demand": [
                        "demand_id", "material_id", "row_key", "demand_period", "quantity", "unit_price",
                        "total_price", "unit", "reporter", "remark", "source_file",
                        "source_release_id",
                    ],
                    "fact_asset": [
                        "asset_code", "asset_name", "row_key", "company", "domain", "user_name", "manager",
                        "location", "purchase_date", "status", "check_result",
                        # T1: ledger-export-plan §7.2 (LD-1/LD-2 锁定 2026-08-10)
                        "material_code", "asset_qty", "unit", "is_instrument", "replace_cycle",
                        "check_cycle", "consumption_plan", "tool_source", "asset_quota_qty",
                        "remark",
                        "source_file", "color_flag", "source_sheet", "source_release_id",
                    ],
                    "fact_stock_flow": [
                        "flow_id", "material_id", "row_key", "flow_type", "flow_date", "quantity", "unit",
                        "person", "purpose", "remark", "parse_level", "parse_source",
                        "source_file", "source_sheet", "source_row", "source_segment",
                        "source_release_id",
                    ],
                    "fact_quota_adjust": [
                        "quota_id", "material_id", "row_key", "adjust_type", "material_code",
                        "material_name", "installed_qty", "accident_quota", "reserve_quota",
                        "verified_quota", "device_name", "reason", "delete_flag",
                        "source_file", "source_release_id",
                    ],
                }
                cols = cols_by_table[table]
                placeholders = ", ".join(["?"] * len(cols))
                col_sql = ", ".join(cols)
                lineage_n = 0
                # P1-5: 所有域发布均镜像血缘到 fact_release_rows（A5.2 由 stock_flow 推广到全部域）
                con.execute(
                    """
                    DELETE FROM fact_release_rows
                    WHERE source_release_id = ? AND target_domain = ?
                    """,
                    [release_id, domain],
                )
                for i, rec in enumerate(mapped):
                    row_key = rec.get("_row_key")
                    if not row_key:
                        if table == "fact_stock_flow":
                            row_key = (
                                f"{rec.get('source_file')}|{rec.get('source_sheet')}|"
                                f"{rec.get('source_row')}|{rec.get('source_segment')}|"
                                f"{rec.get('flow_type')}"
                            )
                        else:
                            mid = rec.get("material_id") or rec.get("asset_code") or f"r{i}"
                            row_key = f"{rec.get('source_file')}|{domain}|{mid}|{i}"
                    # strip helper keys
                    name = rec.pop("_material_name", None)
                    code = rec.pop("_material_code", None)
                    rec.pop("_spec", None)
                    rec.pop("_row_key", None)
                    rec["row_key"] = row_key
                    values = [rec.get(c) for c in cols]
                    if table == "fact_asset":
                        # b3: fact_asset 以 asset_code 为 PK，跨文件存在同码资产
                        # （如「资产清查汇总表」），同码时以本次发布快照覆盖旧台账，
                        # 避免 500 RELEASE_FAILED（原为裸 INSERT 触发主键冲突）。
                        upsert_sets = ", ".join(
                            f"{c} = excluded.{c}" for c in cols if c != "asset_code"
                        )
                        con.execute(
                            f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
                            f"ON CONFLICT (asset_code) DO UPDATE SET {upsert_sets}",
                            values,
                        )
                    else:
                        con.execute(
                            f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})",
                            values,
                        )
                    inserted += 1
                    if table == "fact_stock_flow":
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
                            "row_key": row_key,
                        }
                    else:
                        payload = {c: rec.get(c) for c in cols}
                    con.execute(
                        """
                        INSERT INTO fact_release_rows
                        (source_release_id, file_id, target_domain, row_key, payload_json)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        [
                            release_id,
                            staging["file_id"],
                            domain,
                            row_key,
                            json.dumps(payload, ensure_ascii=False, default=str),
                        ],
                    )
                    lineage_n += 1
                material_ops["fact_inserted"] = inserted
                if lineage_n:
                    material_ops["lineage_rows"] = lineage_n
                if audit_action == "lineage_rebuild":
                    material_ops["rebuilt"] = True

            con.execute(
                """
                INSERT OR REPLACE INTO write_checkpoint (release_id, row_count, target_table, updated_at)
                VALUES (?, ?, ?, current_timestamp)
                """,
                [release_id, inserted, target_table],
            )
        finally:
            con.close()
    finally:
        lock.release()

    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO release_manifest (
                release_id, file_id, config_version, staging_id, clean_rows, blocked_rows,
                material_ops_json, fingerprint, released_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'released')
            ON CONFLICT(release_id) DO UPDATE SET
                clean_rows=excluded.clean_rows,
                blocked_rows=excluded.blocked_rows,
                material_ops_json=excluded.material_ops_json,
                released_by=excluded.released_by,
                released_at=datetime('now'),
                status='released'
            """,
            [
                release_id,
                staging["file_id"],
                staging["config_version"],
                staging["staging_id"],
                inserted,
                int(staging.get("blocked_rows") or 0),
                json.dumps(material_ops, ensure_ascii=False),
                staging.get("fingerprint"),
                actor,
            ],
        )
        con.execute(
            """
            UPDATE staging_record
            SET status='RELEASED', release_id=?, clean_rows=?, updated_at=?
            WHERE staging_id=?
            """,
            [release_id, inserted, _now(), staging["staging_id"]],
        )
        con.execute(
            "UPDATE file_batch SET status='released' WHERE file_id=?",
            [staging["file_id"]],
        )
        con.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES (?, ?, ?, ?)
            """,
            [
                audit_action,
                release_id,
                actor,
                json.dumps(
                    {
                        "file_id": staging["file_id"],
                        "staging_id": staging["staging_id"],
                        "target_domain": staging["target_domain"],
                        "target_table": target_table,
                        "rows": inserted,
                        "material_ops": material_ops,
                        "flow_example_snapshot": example_snapshot,
                        "rebuilt": audit_action == "lineage_rebuild",
                    },
                    ensure_ascii=False,
                ),
            ],
        )
        man = con.execute("SELECT * FROM release_manifest WHERE release_id=?", [release_id]).fetchone()
    return {
        "status": "RELEASED",
        "release": dict(man),
        "idempotent": False,
        "target_table": target_table,
        "rows": inserted,
        "target_domain": staging["target_domain"],
        "audit_action": audit_action,
    }


DOMAIN_FACT_TABLE = {
    "inventory": "fact_inventory",
    "demand": "fact_demand",
    "asset": "fact_asset",
    "stock_flow": "fact_stock_flow",
}


def _resolve_release_staging(release_id: str) -> dict:
    with meta_tx() as con:
        staging = con.execute(
            """
            SELECT * FROM staging_record
            WHERE release_id=?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            [release_id],
        ).fetchone()
        if not staging:
            man = con.execute(
                "SELECT * FROM release_manifest WHERE release_id=?", [release_id]
            ).fetchone()
            if man:
                staging = con.execute(
                    "SELECT * FROM staging_record WHERE staging_id=?",
                    [man["staging_id"]],
                ).fetchone()
        if not staging:
            raise KeyError(f"staging not found for release_id={release_id}")
        return dict(staging)


def lineage_revoke(release_id: str, *, actor: str) -> dict:
    """D6: delete derived rows for a release — no in-place UPDATE / no generic reverse."""
    if not release_id:
        raise ValueError("release_id required")
    staging = _resolve_release_staging(release_id)
    domain = staging.get("target_domain") or "generic"
    if domain == "stock_flow":
        from app.services.flow_lineage import revoke_stock_flow_release

        out = revoke_stock_flow_release(release_id, actor=actor)
        out["target_domain"] = domain
        return out

    table = DOMAIN_FACT_TABLE.get(domain)
    lock = acquire_writer()
    deleted = 0
    deleted_materials = 0
    deleted_lineage = 0
    try:
        con = writer_conn()
        try:
            if table:
                before = con.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE source_release_id = ?",
                    [release_id],
                ).fetchone()[0]
                con.execute(f"DELETE FROM {table} WHERE source_release_id = ?", [release_id])
                deleted = int(before)
            else:
                before = con.execute(
                    "SELECT COUNT(*) FROM fact_release_rows WHERE source_release_id = ?",
                    [release_id],
                ).fetchone()[0]
                deleted = int(before)
            con.execute(
                "DELETE FROM fact_release_rows WHERE source_release_id = ?", [release_id]
            )
            deleted_lineage = deleted  # approximate; exact not required
            mat_before = con.execute(
                "SELECT COUNT(*) FROM dim_material WHERE source_release_id = ?",
                [release_id],
            ).fetchone()[0]
            con.execute("DELETE FROM dim_material WHERE source_release_id = ?", [release_id])
            deleted_materials = int(mat_before)
        finally:
            con.close()
        with meta_tx() as mcon:
            mcon.execute(
                """
                INSERT INTO write_audit (action, release_id, actor, detail_json)
                VALUES ('lineage_revoke', ?, ?, ?)
                """,
                [
                    release_id,
                    actor,
                    json.dumps(
                        {
                            "target_domain": domain,
                            "target_table": table or "fact_release_rows",
                            "deleted_rows": deleted,
                            "deleted_materials": deleted_materials,
                            "deleted_lineage_rows": deleted_lineage,
                        },
                        ensure_ascii=False,
                    ),
                ],
            )
    finally:
        lock.release()
    return {
        "ok": True,
        "release_id": release_id,
        "target_domain": domain,
        "target_table": table or "fact_release_rows",
        "deleted_rows": deleted,
        "deleted_materials": deleted_materials,
        "actor": actor,
    }


def lineage_rebuild(release_id: str, *, actor: str) -> dict:
    """D6: revoke+regenerate from staging parquet (same release_id). Never UPDATE in place."""
    if not release_id:
        raise ValueError("release_id required")
    staging = _resolve_release_staging(release_id)
    domain = staging.get("target_domain") or "generic"

    # stock_flow keeps FL7 path (example snapshot + pending refresh + year-qty audit)
    if domain == "stock_flow":
        from app.services.flow_lineage import rebuild_stock_flow_release

        out = rebuild_stock_flow_release(release_id, actor=actor)
        out["target_domain"] = domain
        return out

    path = staging_payload_path(
        staging["file_id"], staging["config_version"], staging["target_domain"]
    )
    if not path.exists():
        raise FileNotFoundError(f"staging payload missing: {path}")

    written = _write_release(
        staging, release_id=release_id, actor=actor, audit_action="lineage_rebuild"
    )
    return {
        "ok": True,
        "release_id": release_id,
        "target_domain": domain,
        "target_table": written.get("target_table"),
        "rows": written.get("rows"),
        "rebuilt": True,
        "actor": actor,
        "audit_action": "lineage_rebuild",
    }


def list_releases(*, limit: int = 50, offset: int = 0, domain: str | None = None) -> dict:
    """Recent release_manifest rows for Ops lineage UI."""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with meta_tx() as con:
        if domain:
            total = con.execute(
                """
                SELECT COUNT(*) AS c FROM release_manifest m
                JOIN staging_record s ON s.staging_id = m.staging_id
                WHERE s.target_domain = ?
                """,
                [domain],
            ).fetchone()["c"]
            rows = con.execute(
                """
                SELECT m.release_id, m.file_id, m.config_version, m.staging_id,
                       m.clean_rows, m.status, m.released_by, m.released_at,
                       m.supersedes, m.superseded_by,
                       s.target_domain
                FROM release_manifest m
                JOIN staging_record s ON s.staging_id = m.staging_id
                WHERE s.target_domain = ?
                ORDER BY m.released_at DESC
                LIMIT ? OFFSET ?
                """,
                [domain, limit, offset],
            ).fetchall()
        else:
            total = con.execute("SELECT COUNT(*) AS c FROM release_manifest").fetchone()["c"]
            rows = con.execute(
                """
                SELECT m.release_id, m.file_id, m.config_version, m.staging_id,
                       m.clean_rows, m.status, m.released_by, m.released_at,
                       m.supersedes, m.superseded_by,
                       s.target_domain
                FROM release_manifest m
                LEFT JOIN staging_record s ON s.staging_id = m.staging_id
                ORDER BY m.released_at DESC
                LIMIT ? OFFSET ?
                """,
                [limit, offset],
            ).fetchall()
    return {"total": total, "items": [dict(r) for r in rows], "limit": limit, "offset": offset}


def seed_opening_from_snapshot(*, actor: str, dry_run: bool = False) -> dict:
    """Set opening_qty = stock_qty for inventory materials that have no stock_flow rows.

    Semantics (docs/12 §6 PoC): inventory snapshot with no attributed flows ≈ 期初=现存量,
    expected_net=0. Does NOT invent openings for materials that already have flows
    (those remain mismatch / need real 期初 ledger or material_id alignment).
    """
    lock = acquire_writer()
    try:
        con = writer_conn()
        try:
            rel = con.execute(
                """
                SELECT i.inventory_id, i.material_id, i.stock_qty, i.opening_qty, i.source_file
                FROM fact_inventory i
                WHERE NOT EXISTS (
                  SELECT 1 FROM fact_stock_flow f WHERE f.material_id = i.material_id
                )
                  AND COALESCE(i.stock_qty, 0) IS NOT NULL
                  AND ABS(COALESCE(i.stock_qty, 0)) > 1e-12
                  AND (
                    i.opening_qty IS NULL
                    OR ABS(COALESCE(i.opening_qty, 0) - COALESCE(i.stock_qty, 0)) > 1e-12
                  )
                """
            )
            cols = [c[0] for c in rel.description]
            rows = [dict(zip(cols, r)) for r in rel.fetchall()]
            if dry_run:
                return {
                    "dry_run": True,
                    "would_update": len(rows),
                    "sample": rows[:20],
                    "actor": actor,
                }
            updated = 0
            for r in rows:
                con.execute(
                    """
                    UPDATE fact_inventory
                    SET opening_qty = stock_qty
                    WHERE inventory_id = ?
                    """,
                    [r["inventory_id"]],
                )
                updated += 1
        finally:
            con.close()
    finally:
        lock.release()

    with meta_tx() as mcon:
        mcon.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES ('seed_opening_snapshot', NULL, ?, ?)
            """,
            [
                actor,
                json.dumps(
                    {
                        "updated": updated,
                        "policy": "opening_qty=stock_qty where no fact_stock_flow for material_id",
                    },
                    ensure_ascii=False,
                ),
            ],
        )
    return {
        "dry_run": False,
        "updated": updated,
        "policy": "opening_qty=stock_qty where no fact_stock_flow for material_id",
        "actor": actor,
    }


def apply_material_align(*, pairs: list[tuple[str, str]], actor: str) -> dict:
    """Remap fact_stock_flow.material_id from→to (docs/03 master link / 04 §7).

    Does not delete dim rows. Skips pairs where from==to or from has no flow rows.
    """
    cleaned: list[tuple[str, str]] = []
    for a, b in pairs:
        a = (a or "").strip()
        b = (b or "").strip()
        if a and b and a != b:
            cleaned.append((a, b))
    if not cleaned:
        return {"updated_flows": 0, "pairs": 0, "actor": actor}

    lock = acquire_writer()
    updated = 0
    per_pair: list[dict] = []
    try:
        con = writer_conn()
        try:
            for src, dst in cleaned:
                # ensure target dim exists (copy name from source if needed)
                dst_exists = con.execute(
                    "SELECT 1 FROM dim_material WHERE material_id = ?", [dst]
                ).fetchone()
                if not dst_exists:
                    rel = con.execute(
                        """
                        SELECT material_name, spec, unit, category, source_file, source_release_id
                        FROM dim_material WHERE material_id = ?
                        """,
                        [src],
                    )
                    cols = [c[0] for c in rel.description]
                    src_row = rel.fetchone()
                    if src_row:
                        sd = dict(zip(cols, src_row))
                        con.execute(
                            """
                            INSERT INTO dim_material (
                              material_id, material_code, material_name, spec, unit, category,
                              name_alias, spec_alias, source_file, code_source, match_level, source_release_id
                            ) VALUES (?, ?, ?, ?, ?, ?, '', '', ?, 'align', 'L2_align', ?)
                            """,
                            [
                                dst,
                                dst,
                                sd.get("material_name") or "",
                                sd.get("spec") or "",
                                sd.get("unit") or "",
                                sd.get("category") or "",
                                sd.get("source_file") or "",
                                sd.get("source_release_id"),
                            ],
                        )
                before = con.execute(
                    "SELECT COUNT(*) FROM fact_stock_flow WHERE material_id = ?", [src]
                ).fetchone()[0]
                if before:
                    con.execute(
                        "UPDATE fact_stock_flow SET material_id = ? WHERE material_id = ?",
                        [dst, src],
                    )
                updated += int(before or 0)
                per_pair.append({"from": src, "to": dst, "flows": int(before or 0)})
        finally:
            con.close()
    finally:
        lock.release()

    with meta_tx() as mcon:
        mcon.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES ('material_align_apply', NULL, ?, ?)
            """,
            [
                actor,
                json.dumps(
                    {"updated_flows": updated, "pairs": per_pair[:100]},
                    ensure_ascii=False,
                ),
            ],
        )
    return {"updated_flows": updated, "pairs": len(cleaned), "detail": per_pair, "actor": actor}


def master_apply(
    *,
    materials: list[dict],
    actor: str,
    action: str,
) -> dict:
    """Approve / reject / merge master candidates into dim_material (docs/04 §7).

    Only path that marks L3 rows as human-confirmed in DuckDB.
    """
    action = (action or "").strip().lower()
    if action not in ("approve", "reject", "merge"):
        raise ValueError("action must be approve|reject|merge")
    rows = [m for m in (materials or []) if (m.get("material_id") or "").strip()]
    if not rows:
        return {"updated": 0, "action": action, "actor": actor}

    lock = acquire_writer()
    updated = 0
    detail: list[dict] = []
    try:
        con = writer_conn()
        try:
            for m in rows:
                mid = str(m["material_id"]).strip()
                if action == "approve":
                    exists = con.execute(
                        "SELECT 1 FROM dim_material WHERE material_id = ?", [mid]
                    ).fetchone()
                    if exists:
                        con.execute(
                            """
                            UPDATE dim_material SET
                              material_code = COALESCE(NULLIF(?, ''), material_code),
                              material_name = COALESCE(NULLIF(?, ''), material_name),
                              spec = COALESCE(NULLIF(?, ''), spec),
                              unit = COALESCE(NULLIF(?, ''), unit),
                              category = COALESCE(NULLIF(?, ''), category),
                              code_source = 'master_confirm',
                              match_level = 'approved'
                            WHERE material_id = ?
                            """,
                            [
                                m.get("material_code") or "",
                                m.get("material_name") or "",
                                m.get("spec") or "",
                                m.get("unit") or "",
                                m.get("category") or "",
                                mid,
                            ],
                        )
                    else:
                        con.execute(
                            """
                            INSERT INTO dim_material (
                              material_id, material_code, material_name, spec, unit, category,
                              name_alias, spec_alias, source_file, code_source, match_level, source_release_id
                            ) VALUES (?, ?, ?, ?, ?, ?, '', '', ?, 'master_confirm', 'approved', ?)
                            """,
                            [
                                mid,
                                m.get("material_code") or mid,
                                m.get("material_name") or "",
                                m.get("spec") or "",
                                m.get("unit") or "",
                                m.get("category") or "",
                                m.get("source_file") or "",
                                m.get("source_release_id"),
                            ],
                        )
                    updated += 1
                    detail.append({"material_id": mid, "action": "approve"})
                elif action == "reject":
                    con.execute(
                        """
                        UPDATE dim_material
                        SET code_source = 'master_reject', match_level = 'L3_rejected'
                        WHERE material_id = ?
                        """,
                        [mid],
                    )
                    updated += 1
                    detail.append({"material_id": mid, "action": "reject"})
                else:  # merge — flows remapped by apply_material_align; mark source row
                    merge_to = (m.get("merge_to") or "").strip()
                    con.execute(
                        """
                        UPDATE dim_material
                        SET code_source = 'master_merge', match_level = 'merged'
                        WHERE material_id = ?
                        """,
                        [mid],
                    )
                    updated += 1
                    detail.append({"material_id": mid, "action": "merge", "merge_to": merge_to})
        finally:
            con.close()
    finally:
        lock.release()

    with meta_tx() as mcon:
        mcon.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES ('master_apply', NULL, ?, ?)
            """,
            [
                actor,
                json.dumps(
                    {"action": action, "updated": updated, "detail": detail[:100]},
                    ensure_ascii=False,
                ),
            ],
        )
    return {"updated": updated, "action": action, "detail": detail, "actor": actor}
