# -*- coding: utf-8 -*-
"""Flow pending / confirm / reconcile (docs/12 A7–A8)."""
from __future__ import annotations

import json
import uuid
from typing import Any

from app.repositories import biz_conn, meta_conn, meta_tx
from app.services.flow_parse import example_key, text_norm


def _sid() -> str:
    return uuid.uuid4().hex[:12]


def list_pending(
    *,
    limit: int = 50,
    offset: int = 0,
    status: str = "pending",
    parse_level: str | None = None,
) -> dict:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    where = "WHERE status=?"
    params: list[Any] = [status]
    if parse_level:
        where += " AND parse_level=?"
        params.append(parse_level)
    con = meta_conn()
    try:
        total = con.execute(
            f"SELECT COUNT(*) AS c FROM flow_pending {where}", params
        ).fetchone()["c"]
        rows = con.execute(
            f"""
            SELECT * FROM flow_pending
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
    finally:
        con.close()
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["suggested"] = json.loads(d.pop("suggested_json") or "{}")
        except json.JSONDecodeError:
            d["suggested"] = {}
        items.append(d)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def confirm_pending(
    *,
    pending_id: str,
    decision: str,
    actor: str,
    corrected: dict[str, Any] | None = None,
    note: str = "",
    overwrite: bool = False,
) -> dict:
    """decision: accept | amend | ignore. overwrite=True updates conflicting flow_example."""
    decision = (decision or "").lower().strip()
    if decision not in ("accept", "amend", "ignore"):
        raise ValueError("decision must be accept|amend|ignore")
    with meta_tx() as con:
        row = con.execute("SELECT * FROM flow_pending WHERE pending_id=?", [pending_id]).fetchone()
        if not row:
            raise KeyError("pending not found")
        row = dict(row)
        if row["status"] not in ("pending", "conflict"):
            return {"ok": True, "idempotent": True, "pending_id": pending_id, "status": row["status"]}

        suggested = {}
        try:
            suggested = json.loads(row.get("suggested_json") or "{}")
        except json.JSONDecodeError:
            pass
        final = dict(suggested)
        if decision == "amend" and corrected:
            final.update(corrected)
        if decision == "ignore":
            # negative example — L3
            final = {
                "parse_level": "L3",
                "quantity": None,
                "flow_date": None,
                "remark": row.get("text_raw") or "",
                "flow_type": row.get("flow_type") or "OUT",
                "flags": ["manual_ignore"],
            }
            level = "L3"
        else:
            level = str(final.get("parse_level") or "L2")
            if decision == "accept" and level == "L3":
                level = "L2"
            final["parse_level"] = level
            final["parse_source"] = "manual"

        tn = row.get("text_norm") or text_norm(row.get("text_raw") or "")
        # conflict: different JSON for same text_norm already exists
        existing = con.execute(
            "SELECT example_id, flow_json FROM flow_example WHERE text_norm=?", [tn]
        ).fetchone()
        flow_json = json.dumps([final], ensure_ascii=False, default=str)
        if existing and existing["flow_json"] != flow_json and decision != "ignore" and not overwrite:
            con.execute(
                "UPDATE flow_pending SET conflict=1, status='conflict', version=version+1, updated_at=datetime('now') WHERE pending_id=?",
                [pending_id],
            )
            return {
                "ok": False,
                "code": "FLOW_EXAMPLE_CONFLICT",
                "pending_id": pending_id,
                "conflict": True,
                "existing_example_id": existing["example_id"],
            }

        eid = existing["example_id"] if existing else f"ex_{_sid()}"
        if existing:
            con.execute(
                """
                UPDATE flow_example
                SET flow_json=?, level=?, hits=hits+1, confirmed_by=?, updated_at=datetime('now')
                WHERE example_id=?
                """,
                [flow_json, level, actor, eid],
            )
        else:
            con.execute(
                """
                INSERT INTO flow_example (example_id, text_norm, flow_json, level, hits, confirmed_by)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                [eid, tn, flow_json, level, actor],
            )

        new_status = "ignored" if decision == "ignore" else "confirmed"
        con.execute(
            """
            UPDATE flow_pending
            SET status=?, suggested_json=?, conflict=0, version=version+1, updated_at=datetime('now')
            WHERE pending_id=?
            """,
            [new_status, flow_json, pending_id],
        )
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('flow_confirm', ?, ?, ?, ?)
            """,
            [pending_id, decision + ("+overwrite" if overwrite else ""), (note or "")[:200], actor],
        )
    return {
        "ok": True,
        "pending_id": pending_id,
        "decision": decision,
        "example_id": eid,
        "level": level,
        "actor": actor,
        "overwrite": overwrite,
    }


def reconcile(*, persist: bool = False) -> dict:
    """ΣIN−ΣOUT ≟ stock_qty − opening_qty (docs/12 §6 / A7.1); gaps allowed (FL6).

    opening_qty from fact_inventory; NULL treated as 0 (PoC when ledger has no 期初).
    persist=False (default): compute only — safe for GET/gate/overview.
    persist=True: rewrite meta.flow_reconcile_gap (explicit ops POST only).

    gap_class:
      inv_only   — inventory present, no flows for material_id
      flow_only  — flows present, no inventory row
      mismatch   — both present but nets disagree
    """
    formula = "flow_net(ΣIN−ΣOUT) ≟ stock_qty − COALESCE(opening_qty,0)"
    con = biz_conn()
    try:
        df = con.execute(
            """
            WITH flow AS (
              SELECT material_id,
                     SUM(CASE WHEN flow_type='IN' THEN COALESCE(quantity,0) ELSE 0 END) AS qty_in,
                     SUM(CASE WHEN flow_type='OUT' THEN COALESCE(quantity,0) ELSE 0 END) AS qty_out
              FROM fact_stock_flow
              GROUP BY material_id
            ),
            inv AS (
              SELECT material_id,
                     SUM(COALESCE(stock_qty,0)) AS stock_qty,
                     SUM(COALESCE(opening_qty,0)) AS opening_qty,
                     ANY_VALUE(source_file) AS source_file
              FROM fact_inventory
              GROUP BY material_id
            )
            SELECT COALESCE(i.material_id, f.material_id) AS material_id,
                   COALESCE(i.stock_qty, 0) AS stock_qty,
                   COALESCE(i.opening_qty, 0) AS opening_qty,
                   COALESCE(i.stock_qty, 0) - COALESCE(i.opening_qty, 0) AS expected_net,
                   COALESCE(f.qty_in, 0) - COALESCE(f.qty_out, 0) AS flow_net,
                   (COALESCE(f.qty_in, 0) - COALESCE(f.qty_out, 0))
                     - (COALESCE(i.stock_qty, 0) - COALESCE(i.opening_qty, 0)) AS gap,
                   i.source_file,
                   CASE
                     WHEN i.material_id IS NULL THEN 'flow_only'
                     WHEN f.material_id IS NULL THEN 'inv_only'
                     ELSE 'mismatch'
                   END AS gap_class
            FROM inv i
            FULL OUTER JOIN flow f USING (material_id)
            WHERE ABS(
              (COALESCE(f.qty_in, 0) - COALESCE(f.qty_out, 0))
              - (COALESCE(i.stock_qty, 0) - COALESCE(i.opening_qty, 0))
            ) > 0.01
            ORDER BY ABS(
              (COALESCE(f.qty_in, 0) - COALESCE(f.qty_out, 0))
              - (COALESCE(i.stock_qty, 0) - COALESCE(i.opening_qty, 0))
            ) DESC
            LIMIT 5000
            """
        ).fetchdf()
        opening_populated = con.execute(
            """
            SELECT COUNT(*) AS c FROM fact_inventory
            WHERE opening_qty IS NOT NULL AND ABS(opening_qty) > 1e-12
            """
        ).fetchone()[0]
        overlap = con.execute(
            """
            SELECT COUNT(*) AS c FROM (
              SELECT material_id FROM fact_inventory
              INTERSECT
              SELECT material_id FROM fact_stock_flow
            )
            """
        ).fetchone()[0]
    finally:
        con.close()

    gaps_raw = df.to_dict(orient="records") if len(df) else []
    gaps: list[dict] = []
    by_class: dict[str, int] = {"inv_only": 0, "flow_only": 0, "mismatch": 0}
    for g in gaps_raw:
        row: dict = {}
        for k, v in g.items():
            if v is None:
                row[k] = None
                continue
            if hasattr(v, "item"):
                try:
                    v = v.item()
                except Exception:
                    v = None
            if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
                row[k] = None
            else:
                row[k] = v
        cls = str(row.get("gap_class") or "mismatch")
        by_class[cls] = by_class.get(cls, 0) + 1
        gaps.append(row)
    if persist:
        with meta_tx() as mcon:
            mcon.execute("DELETE FROM flow_reconcile_gap")
            for g in gaps:
                mcon.execute(
                    """
                    INSERT INTO flow_reconcile_gap (material_id, stock_qty, flow_net, gap, source_file)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        g.get("material_id"),
                        g.get("stock_qty"),
                        g.get("flow_net"),
                        g.get("gap"),
                        g.get("source_file"),
                    ],
                )
    return {
        "total": len(gaps),
        "threshold": 0.01,
        "formula": formula,
        "opening_mode": "fact_inventory.opening_qty",
        "opening_default": 0,
        "opening_populated_rows": int(opening_populated or 0),
        "material_id_overlap": int(overlap or 0),
        "by_class": by_class,
        "note": (
            "PoC: missing opening_qty treated as 0. "
            "inv_only: seed opening=stock via POST /govern/flow/opening/seed. "
            "flow_only/mismatch: need material_id alignment or real 期初 — 不宣称账已轧平."
        ),
        "items": gaps[:200],
    }


def parse_stats() -> dict:
    """A9.1 — L1/L2/L3 counts, aggregatable by source_file / sheet."""
    con = biz_conn()
    try:
        rows = con.execute(
            """
            SELECT parse_level, COUNT(*) AS c
            FROM fact_stock_flow
            GROUP BY parse_level
            """
        ).fetchall()
        by_level = {r[0] or "?": int(r[1]) for r in rows}
        total = sum(by_level.values())

        by_file_rows = con.execute(
            """
            SELECT COALESCE(source_file, '') AS source_file,
                   parse_level, COUNT(*) AS c
            FROM fact_stock_flow
            GROUP BY 1, 2
            ORDER BY 1, 2
            """
        ).fetchall()
        by_sheet_rows = con.execute(
            """
            SELECT COALESCE(source_file, '') AS source_file,
                   COALESCE(source_sheet, '') AS source_sheet,
                   parse_level, COUNT(*) AS c
            FROM fact_stock_flow
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3
            """
        ).fetchall()
    finally:
        con.close()

    by_file: dict[str, dict[str, int]] = {}
    for r in by_file_rows:
        sf, lvl, c = r[0], r[1] or "?", int(r[2])
        by_file.setdefault(sf, {})[lvl] = c

    by_sheet: list[dict] = []
    for r in by_sheet_rows:
        by_sheet.append(
            {
                "source_file": r[0],
                "source_sheet": r[1],
                "parse_level": r[2] or "?",
                "count": int(r[3]),
            }
        )

    mcon = meta_conn()
    try:
        pending = mcon.execute(
            "SELECT COUNT(*) AS c FROM flow_pending WHERE status='pending'"
        ).fetchone()["c"]
        pending_by_level = mcon.execute(
            """
            SELECT COALESCE(parse_level, '?') AS parse_level, COUNT(*) AS c
            FROM flow_pending WHERE status='pending'
            GROUP BY 1
            """
        ).fetchall()
    finally:
        mcon.close()

    l1 = by_level.get("L1", 0)
    l1l2 = l1 + by_level.get("L2", 0)
    return {
        "published_by_level": by_level,
        "published_total": total,
        "l1_ratio": round(l1 / total, 4) if total else None,
        "l1_over_l1l2": round(l1 / l1l2, 4) if l1l2 else None,
        "pending": pending,
        "pending_by_level": {r[0]: int(r[1]) for r in pending_by_level},
        "by_source_file": by_file,
        "by_source_sheet": by_sheet,
    }
