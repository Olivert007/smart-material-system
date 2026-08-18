# -*- coding: utf-8 -*-
"""Material ID alignment: flow synthetic IDs → inventory/master codes (docs/03 L1–L2 / 04 §7).

Never silently pick among multi-candidate matches (C4). Unique high-confidence
proposals may be batch-accepted by ops; ambiguous stay proposed for human.
"""
from __future__ import annotations

import re
import uuid
from difflib import SequenceMatcher
from typing import Any

from app.repositories import biz_conn, meta_conn, meta_tx


def _sid() -> str:
    return uuid.uuid4().hex[:12]


def norm_text(s: str | None) -> str:
    s = (s or "").strip().lower()
    return re.sub(r"[\s\-_/\\（）()【】\[\]·•,，.。:：;；*×x]+", "", s)


def score_name_spec(
    name_a: str, spec_a: str, name_b: str, spec_b: str
) -> tuple[float, str]:
    """Return (score, match_kind). score < 0.9 means no proposal."""
    fn, fs = norm_text(name_a), norm_text(spec_a)
    inn, inns = norm_text(name_b), norm_text(spec_b)
    if not fn or not inn:
        return 0.0, "none"
    if fn == inn:
        if fs and inns and fs == inns:
            return 1.0, "L2_name_spec"
        if not fs or not inns:
            return 0.98, "L2_name"
        return 0.95, "L2_name_spec_partial"
    # containment: reject ultra-short / overly loose
    if len(fn) >= 4 and (fn in inn or inn in fn):
        shorter, longer = (fn, inn) if len(fn) <= len(inn) else (inn, fn)
        if len(longer) / max(len(shorter), 1) <= 2.5:
            return 0.9, "L2_contain"
    ratio = SequenceMatcher(None, fn, inn).ratio()
    if ratio >= 0.92 and len(fn) >= 4 and len(inn) >= 4:
        return float(ratio), "L2_fuzzy"
    return 0.0, "none"


def _inventory_universe() -> list[dict[str, str]]:
    con = biz_conn()
    try:
        rel = con.execute(
            """
            SELECT DISTINCT i.material_id AS material_id,
                   COALESCE(d.material_code, '') AS material_code,
                   COALESCE(d.material_name, '') AS material_name,
                   COALESCE(d.spec, '') AS spec
            FROM fact_inventory i
            LEFT JOIN dim_material d USING (material_id)
            """
        )
        cols = [c[0] for c in rel.description]
        return [dict(zip(cols, r)) for r in rel.fetchall()]
    finally:
        con.close()


def _flow_materials() -> list[dict[str, str]]:
    con = biz_conn()
    try:
        rel = con.execute(
            """
            SELECT DISTINCT f.material_id AS material_id,
                   COALESCE(d.material_code, '') AS material_code,
                   COALESCE(d.material_name, '') AS material_name,
                   COALESCE(d.spec, '') AS spec
            FROM fact_stock_flow f
            LEFT JOIN dim_material d USING (material_id)
            WHERE f.material_id NOT IN (SELECT material_id FROM fact_inventory)
            """
        )
        cols = [c[0] for c in rel.description]
        return [dict(zip(cols, r)) for r in rel.fetchall()]
    finally:
        con.close()


def match_one(
    *,
    code: str,
    name: str,
    spec: str,
    universe: list[dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    """Best unique match against inventory universe, or None if none/ambiguous."""
    universe = universe if universe is not None else _inventory_universe()
    code = (code or "").strip()
    if code:
        for u in universe:
            if code == (u.get("material_code") or "") or code == (u.get("material_id") or ""):
                return {
                    "to_material_id": u["material_id"],
                    "to_name": u.get("material_name") or "",
                    "score": 1.0,
                    "match_kind": "L1_code",
                    "unique": True,
                }
    cands: list[tuple[float, str, str, str]] = []
    for u in universe:
        sc, kind = score_name_spec(name, spec, u.get("material_name") or "", u.get("spec") or "")
        if sc >= 0.9:
            cands.append((sc, kind, u["material_id"], u.get("material_name") or ""))
    cands.sort(key=lambda x: (-x[0], x[2]))
    if not cands:
        return None
    if len(cands) == 1 or (cands[0][0] - cands[1][0] >= 0.05 and cands[0][0] >= 0.95):
        sc, kind, tid, tname = cands[0]
        return {
            "to_material_id": tid,
            "to_name": tname,
            "score": sc,
            "match_kind": kind,
            "unique": True,
            "alternates": [{"to_material_id": c[2], "score": c[0], "kind": c[1]} for c in cands[1:4]],
        }
    return {
        "to_material_id": cands[0][2],
        "to_name": cands[0][3],
        "score": cands[0][0],
        "match_kind": cands[0][1],
        "unique": False,
        "alternates": [{"to_material_id": c[2], "score": c[0], "kind": c[1], "to_name": c[3]} for c in cands[:5]],
    }


def accepted_maps() -> dict[str, str]:
    """from_material_id → to_material_id for status=accepted."""
    con = meta_conn()
    try:
        rows = con.execute(
            "SELECT from_material_id, to_material_id FROM material_align WHERE status='accepted'"
        ).fetchall()
        return {r["from_material_id"]: r["to_material_id"] for r in rows}
    finally:
        con.close()


def resolve_material_id(
    *,
    code: str | None,
    name: str | None,
    spec: str | None,
    file_id: str,
    row_index: int,
    sheet: str | None = None,
    universe: list[dict[str, str]] | None = None,
    maps: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Intake-time resolve: accepted map / unique L1–L2 / else synthetic M-{file}-{sheet}-{row}."""
    code = (code or "").strip()
    name = name or ""
    spec = spec or ""
    token = re.sub(r"\s+", "", str(sheet or "").strip())[:24] or "row"
    synthetic = code or f"M-{file_id}-{token}-{row_index}"
    maps = maps if maps is not None else accepted_maps()
    if synthetic in maps:
        return maps[synthetic], {"match_kind": "accepted_map", "score": 1.0}
    hit = match_one(code=code, name=name, spec=spec, universe=universe)
    if hit and hit.get("unique"):
        return hit["to_material_id"], hit
    return synthetic, hit if hit and not hit.get("unique") else None


def propose_alignment(*, replace_proposed: bool = True) -> dict[str, Any]:
    """Scan flow-only materials; upsert proposed/ambiguous rows into material_align."""
    universe = _inventory_universe()
    flows = _flow_materials()
    unique_n = amb_n = none_n = 0
    items: list[dict[str, Any]] = []
    with meta_tx() as con:
        if replace_proposed:
            con.execute("DELETE FROM material_align WHERE status='proposed'")
        for fr in flows:
            fid = fr["material_id"]
            # skip already accepted
            existing = con.execute(
                "SELECT status FROM material_align WHERE from_material_id=? AND status='accepted'",
                [fid],
            ).fetchone()
            if existing:
                continue
            hit = match_one(
                code=fr.get("material_code") or "",
                name=fr.get("material_name") or "",
                spec=fr.get("spec") or "",
                universe=universe,
            )
            if not hit:
                none_n += 1
                continue
            status = "proposed" if hit.get("unique") else "proposed"
            note = "" if hit.get("unique") else "ambiguous"
            if hit.get("unique"):
                unique_n += 1
            else:
                amb_n += 1
            aid = f"al_{_sid()}"
            con.execute(
                """
                INSERT INTO material_align (
                  align_id, from_material_id, to_material_id, from_name, to_name,
                  score, match_kind, status, note, actor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(from_material_id, to_material_id) DO UPDATE SET
                  score=excluded.score,
                  match_kind=excluded.match_kind,
                  status=CASE WHEN material_align.status='accepted' THEN material_align.status ELSE excluded.status END,
                  note=excluded.note,
                  from_name=excluded.from_name,
                  to_name=excluded.to_name,
                  updated_at=datetime('now')
                """,
                [
                    aid,
                    fid,
                    hit["to_material_id"],
                    fr.get("material_name") or "",
                    hit.get("to_name") or "",
                    float(hit["score"]),
                    hit["match_kind"],
                    status,
                    note,
                    "system",
                ],
            )
            items.append(
                {
                    "from_material_id": fid,
                    "to_material_id": hit["to_material_id"],
                    "from_name": fr.get("material_name") or "",
                    "to_name": hit.get("to_name") or "",
                    "score": hit["score"],
                    "match_kind": hit["match_kind"],
                    "unique": bool(hit.get("unique")),
                    "alternates": hit.get("alternates") or [],
                }
            )
    return {
        "scanned": len(flows),
        "unique": unique_n,
        "ambiguous": amb_n,
        "unmatched": none_n,
        "inventory_universe": len(universe),
        "items": items[:100],
    }


def list_alignments(*, status: str | None = "proposed", limit: int = 100, offset: int = 0) -> dict:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    con = meta_conn()
    try:
        if status:
            total = con.execute(
                "SELECT COUNT(*) AS c FROM material_align WHERE status=?", [status]
            ).fetchone()["c"]
            rows = con.execute(
                """
                SELECT * FROM material_align WHERE status=?
                ORDER BY score DESC, updated_at DESC
                LIMIT ? OFFSET ?
                """,
                [status, limit, offset],
            ).fetchall()
        else:
            total = con.execute("SELECT COUNT(*) AS c FROM material_align").fetchone()["c"]
            rows = con.execute(
                """
                SELECT * FROM material_align
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                [limit, offset],
            ).fetchall()
    finally:
        con.close()
    return {"total": total, "limit": limit, "offset": offset, "items": [dict(r) for r in rows]}


def confirm_alignment(
    *,
    align_id: str | None = None,
    from_material_id: str | None = None,
    to_material_id: str | None = None,
    decision: str,
    actor: str,
    note: str = "",
    apply_biz: bool = True,
) -> dict:
    """decision: accept | reject. accept optionally remaps fact_stock_flow via writer."""
    decision = (decision or "").lower().strip()
    if decision not in ("accept", "reject"):
        raise ValueError("decision must be accept|reject")
    with meta_tx() as con:
        if align_id:
            row = con.execute("SELECT * FROM material_align WHERE align_id=?", [align_id]).fetchone()
        elif from_material_id and to_material_id:
            row = con.execute(
                "SELECT * FROM material_align WHERE from_material_id=? AND to_material_id=?",
                [from_material_id, to_material_id],
            ).fetchone()
        else:
            raise ValueError("align_id or from_material_id+to_material_id required")
        if not row:
            raise KeyError("alignment not found")
        row = dict(row)
        new_status = "accepted" if decision == "accept" else "rejected"
        con.execute(
            """
            UPDATE material_align
            SET status=?, note=?, actor=?, version=version+1, updated_at=datetime('now')
            WHERE align_id=?
            """,
            [new_status, (note or row.get("note") or "")[:200], actor, row["align_id"]],
        )
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('material_align', ?, ?, ?, ?)
            """,
            [row["align_id"], decision, (note or "")[:200], actor],
        )
    applied = None
    if decision == "accept" and apply_biz:
        from app.services.writer import apply_material_align

        applied = apply_material_align(
            pairs=[(row["from_material_id"], row["to_material_id"])],
            actor=actor,
        )
    return {"ok": True, "align_id": row["align_id"], "status": new_status, "applied": applied}


def accept_unique_proposed(*, actor: str, min_score: float = 0.95, apply_biz: bool = True) -> dict:
    """Batch-accept unique (non-ambiguous) proposals at/above min_score."""
    con = meta_conn()
    try:
        rows = con.execute(
            """
            SELECT * FROM material_align
            WHERE status='proposed' AND IFNULL(note,'') != 'ambiguous' AND score >= ?
            """,
            [min_score],
        ).fetchall()
        rows = [dict(r) for r in rows]
    finally:
        con.close()
    accepted = 0
    pairs: list[tuple[str, str]] = []
    for r in rows:
        confirm_alignment(
            align_id=r["align_id"],
            decision="accept",
            actor=actor,
            note=f"batch-unique score>={min_score}",
            apply_biz=False,
        )
        pairs.append((r["from_material_id"], r["to_material_id"]))
        accepted += 1
    applied = None
    if apply_biz and pairs:
        from app.services.writer import apply_material_align

        applied = apply_material_align(pairs=pairs, actor=actor)
    return {"accepted": accepted, "min_score": min_score, "applied": applied}
