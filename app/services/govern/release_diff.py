# -*- coding: utf-8 -*-
"""Release version diff over fact_release_rows (roadmap §4 / P1-4)."""
from __future__ import annotations

import json
from typing import Any

from app.repositories import biz_conn, meta_tx


def _load_rows(release_id: str) -> dict[str, dict[str, Any]]:
    con = biz_conn()
    try:
        rel = con.execute(
            """
            SELECT row_key, payload_json, target_domain
            FROM fact_release_rows
            WHERE source_release_id = ?
            """,
            [release_id],
        )
        cols = [c[0] for c in rel.description]
        out: dict[str, dict[str, Any]] = {}
        for r in rel.fetchall():
            d = dict(zip(cols, r))
            key = str(d.get("row_key") or "")
            try:
                payload = json.loads(d.get("payload_json") or "{}")
            except json.JSONDecodeError:
                payload = {"_raw": d.get("payload_json")}
            out[key] = {"payload": payload, "target_domain": d.get("target_domain")}
        return out
    finally:
        con.close()


def _field_diff(a: dict, b: dict, *, limit: int = 20) -> list[dict]:
    keys = sorted(set(a) | set(b))
    diffs = []
    for k in keys:
        if a.get(k) != b.get(k):
            diffs.append({"field": k, "old": a.get(k), "new": b.get(k)})
            if len(diffs) >= limit:
                break
    return diffs


def diff_releases(
    release_a: str,
    release_b: str,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    """Compare two releases by row_key → added / removed / changed."""
    if not release_a or not release_b:
        raise ValueError("release_a and release_b required")
    if release_a == release_b:
        raise ValueError("release_a and release_b must differ")

    a = _load_rows(release_a)
    b = _load_rows(release_b)
    keys_a, keys_b = set(a), set(b)

    added = []
    removed = []
    changed = []
    for k in sorted(keys_b - keys_a):
        added.append({"row_key": k, "payload": b[k]["payload"]})
        if len(added) >= limit:
            break
    for k in sorted(keys_a - keys_b):
        removed.append({"row_key": k, "payload": a[k]["payload"]})
        if len(removed) >= limit:
            break
    for k in sorted(keys_a & keys_b):
        if a[k]["payload"] != b[k]["payload"]:
            changed.append(
                {
                    "row_key": k,
                    "fields": _field_diff(a[k]["payload"], b[k]["payload"]),
                }
            )
            if len(changed) >= limit:
                break

    return {
        "ok": True,
        "release_a": release_a,
        "release_b": release_b,
        "counts": {
            "a": len(a),
            "b": len(b),
            "added": len(keys_b - keys_a),
            "removed": len(keys_a - keys_b),
            "changed": sum(
                1 for k in (keys_a & keys_b) if a[k]["payload"] != b[k]["payload"]
            ),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
        "truncated": len(added) + len(removed) + len(changed) >= limit,
        "hint": "对比基于 fact_release_rows；查询层不自动排除 superseded（D1 方案 A）",
    }


def mark_supersede(*, newer_release_id: str, older_release_id: str, actor: str) -> dict:
    """Link supersedes / superseded_by on release_manifest (meta only)."""
    if newer_release_id == older_release_id:
        raise ValueError("releases must differ")
    with meta_tx() as con:
        newer = con.execute(
            "SELECT * FROM release_manifest WHERE release_id=?", [newer_release_id]
        ).fetchone()
        older = con.execute(
            "SELECT * FROM release_manifest WHERE release_id=?", [older_release_id]
        ).fetchone()
        if not newer or not older:
            raise KeyError("release not found")
        con.execute(
            "UPDATE release_manifest SET supersedes=? WHERE release_id=?",
            [older_release_id, newer_release_id],
        )
        con.execute(
            "UPDATE release_manifest SET superseded_by=? WHERE release_id=?",
            [newer_release_id, older_release_id],
        )
        con.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES ('release_supersede', ?, ?, ?)
            """,
            [
                newer_release_id,
                actor,
                json.dumps(
                    {"supersedes": older_release_id, "actor": actor},
                    ensure_ascii=False,
                ),
            ],
        )
    return {
        "ok": True,
        "release_id": newer_release_id,
        "supersedes": older_release_id,
        "actor": actor,
    }
