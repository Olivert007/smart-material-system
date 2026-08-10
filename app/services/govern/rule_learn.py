# -*- coding: utf-8 -*-
"""Rule learning candidates from staging_blocked (roadmap §3.4) — propose only."""
from __future__ import annotations

import json
import uuid
from typing import Any

from app.repositories import meta_tx


def _sid(n: int = 10) -> str:
    return uuid.uuid4().hex[:n]


def propose_from_blocked(*, limit: int = 50, min_count: int = 2) -> dict[str, Any]:
    """Aggregate blocked reasons → govern_confirm(source=rule_learn) candidates.

    Never auto-writes rule_dict / value_rule.
    """
    with meta_tx() as con:
        rows = con.execute(
            """
            SELECT target_domain, header, reason_code, reason_detail, COUNT(*) AS c
            FROM staging_blocked
            GROUP BY target_domain, header, reason_code, reason_detail
            HAVING c >= ?
            ORDER BY c DESC
            LIMIT ?
            """,
            [max(1, min_count), max(1, min(limit, 200))],
        ).fetchall()

    created = 0
    items: list[dict[str, Any]] = []
    with meta_tx() as con:
        for r in rows:
            domain = r["target_domain"] or "inventory"
            header = (r["header"] or "").strip()
            code = r["reason_code"] or ""
            detail = r["reason_detail"] or ""
            cnt = int(r["c"] or 0)
            if code == "UNKNOWN_HEADER" and header:
                kind = "map_alias"
                proposal = {
                    "kind": kind,
                    "domain": domain,
                    "header": header,
                    "suggested_std_field": None,
                    "count": cnt,
                    "hint": "高频未知表头，请人工确认映射后写入 rule_dict",
                }
            elif code in ("VALUE_RANGE", "MISSING_COL", "REQUIRED") or "required" in detail.lower():
                kind = "value_rule"
                std_field = header or "unknown"
                proposal = {
                    "kind": kind,
                    "domain": domain,
                    "std_field": std_field,
                    "check_type": "required" if code in ("MISSING_COL", "REQUIRED") else "numeric_positive",
                    "severity": "block",
                    "count": cnt,
                    "hint": "高频阻断字段，建议新增/激活 value_rule（确认后生效）",
                }
            else:
                kind = "review"
                proposal = {
                    "kind": kind,
                    "domain": domain,
                    "header": header,
                    "reason_code": code,
                    "count": cnt,
                    "hint": detail or "请人工复核",
                }

            # de-dupe open candidates with same fingerprint
            fp = json.dumps(
                {"kind": kind, "domain": domain, "header": header, "code": code},
                ensure_ascii=False,
                sort_keys=True,
            )
            exists = con.execute(
                """
                SELECT id FROM govern_confirm
                WHERE source='rule_learn' AND decision='proposed' AND detail LIKE ?
                LIMIT 1
                """,
                [f"%{header}%{code}%"],
            ).fetchone()
            if exists and header:
                continue
            detail_json = json.dumps({**proposal, "fingerprint": fp}, ensure_ascii=False)
            con.execute(
                """
                INSERT INTO govern_confirm (source, detail, decision, note, actor)
                VALUES ('rule_learn', ?, 'proposed', ?, 'system:rule_learn')
                """,
                [detail_json, f"count={cnt}"],
            )
            created += 1
            items.append(proposal)

    return {
        "ok": True,
        "scanned_groups": len(rows),
        "created": created,
        "items": items[:limit],
        "hint": "候选仅写入 govern_confirm；确认后才回写 rule_dict/value_rule",
    }


def list_candidates(*, limit: int = 50) -> dict[str, Any]:
    with meta_tx() as con:
        rows = con.execute(
            """
            SELECT id, source, detail, decision, note, actor, created_at
            FROM govern_confirm
            WHERE source='rule_learn'
            ORDER BY id DESC
            LIMIT ?
            """,
            [max(1, min(limit, 200))],
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["proposal"] = json.loads(d.get("detail") or "{}")
        except Exception:
            d["proposal"] = {}
        items.append(d)
    return {"total": len(items), "items": items}


def confirm_candidate(
    *,
    confirm_id: int,
    decision: str,
    actor: str,
    std_field: str | None = None,
) -> dict[str, Any]:
    """Accept/reject a rule_learn candidate. Accept may write rule_dict or value_rule."""
    decision = (decision or "").strip().lower()
    if decision not in ("accepted", "rejected"):
        raise ValueError("decision must be accepted|rejected")
    with meta_tx() as con:
        row = con.execute(
            "SELECT * FROM govern_confirm WHERE id=? AND source='rule_learn'",
            [confirm_id],
        ).fetchone()
        if not row:
            raise KeyError("candidate not found")
        if row["decision"] != "proposed":
            raise RuntimeError(f"already decided: {row['decision']}")
        try:
            proposal = json.loads(row["detail"] or "{}")
        except Exception:
            proposal = {}
        applied = None
        if decision == "accepted":
            kind = proposal.get("kind")
            domain = proposal.get("domain") or "inventory"
            if kind == "map_alias":
                header = (proposal.get("header") or "").strip()
                field = (std_field or proposal.get("suggested_std_field") or "").strip()
                if not header or not field:
                    raise ValueError("map_alias accept requires std_field")
                con.execute(
                    """
                    INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
                    VALUES (?, ?, ?, 1, 'rule_learn', ?)
                    ON CONFLICT(header, business_domain, std_field) DO UPDATE SET
                        hits=COALESCE(rule_dict.hits,0)+1,
                        source='rule_learn',
                        confirmed_by=excluded.confirmed_by
                    """,
                    [header, field, domain, actor],
                )
                applied = {"rule_dict": {"header": header, "std_field": field, "domain": domain}}
            elif kind == "value_rule":
                rid = f"vr_learn_{_sid(8)}"
                con.execute(
                    """
                    INSERT INTO value_rule (
                        rule_id, domain, std_field, check_type, params_json,
                        severity, status, confirmed_by
                    ) VALUES (?, ?, ?, ?, '{}', ?, 'active', ?)
                    """,
                    [
                        rid,
                        domain,
                        proposal.get("std_field") or "unknown",
                        proposal.get("check_type") or "required",
                        proposal.get("severity") or "block",
                        actor,
                    ],
                )
                applied = {"value_rule": rid}
        con.execute(
            """
            UPDATE govern_confirm
            SET decision=?, note=?, actor=?
            WHERE id=?
            """,
            [decision, json.dumps(applied or {}, ensure_ascii=False), actor, confirm_id],
        )
    return {"ok": True, "id": confirm_id, "decision": decision, "applied": applied}
