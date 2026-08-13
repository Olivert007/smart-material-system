# -*- coding: utf-8 -*-
"""rule_dict self-learning lookups (docs/04 §6) — read path for map-suggest / resolve_columns."""
from __future__ import annotations

import json
from typing import Any

from app.repositories import meta_conn, meta_tx
from app.services.mapping import ALIASES, _canon_header, _norm

# map-suggest STD_FIELDS names ↔ domain ALIASES keys used by resolve_columns
_STD_TO_DOMAIN: dict[str, list[str]] = {
    "item_name": ["material_name", "asset_name", "item_name"],
    "specification": ["spec", "specification"],
    "keeper_or_user": ["custodian", "user_name", "manager", "keeper_or_user"],
    "quantity": ["stock_qty", "quantity", "qty_in", "qty_out"],
    "material_code": ["material_code", "asset_code"],
    "asset_code": ["asset_code", "material_code"],
    "asset_name": ["asset_name", "material_name"],
    "serial_or_factory_no": ["serial_no", "serial_or_factory_no"],
}

# 0.5 种子规则：修复 stage1 映射 miss（填报人/单价 → ignore）。
# 与 embed_recall.STD_FIELDS 别名口径一致，保证 rule-first 映射命中。
_DEFAULT_RULES: list[dict[str, str]] = [
    {"header": "填报人", "std_field": "keeper_or_user"},
    {"header": "单价", "std_field": "stock_value"},
]

# 旧版 meta.sqlite 的 rule_dict 可能缺以下列；接口层幂等补齐，避免 500。
_RULE_DICT_SCHEMA_EXTRA: list[tuple[str, str]] = [
    ("status", "TEXT NOT NULL DEFAULT 'active'"),
    ("changed_by", "TEXT"),
    ("updated_at", "TEXT"),
]


def ensure_rule_dict_schema(con=None) -> None:
    """幂等补齐 rule_dict 缺失列（旧 meta.sqlite 可能缺 status/changed_by/updated_at）。

    在查询/写入 rule_dict 前调用，保证即使启动迁移未执行页面接口也不会 500。
    """
    owns = con is None
    con = con or meta_conn()
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(rule_dict)").fetchall()}
        for name, ddl in _RULE_DICT_SCHEMA_EXTRA:
            if name not in cols:
                con.execute(f"ALTER TABLE rule_dict ADD COLUMN {name} {ddl}")
        con.commit()
    finally:
        if owns:
            con.close()


def ensure_seed_rules(*, actor: str = "system:seed") -> dict:
    """幂等写入 default 域种子规则（INSERT OR IGNORE 语义）。"""
    # schema 兜底在事务外执行，避免提前 commit 破坏 meta_tx 原子性
    ensure_rule_dict_schema()
    inserted = 0
    existing = 0
    with meta_tx() as con:
        for r in _DEFAULT_RULES:
            row = con.execute(
                "SELECT rule_id FROM rule_dict WHERE header=? AND business_domain='default' AND std_field=?",
                [r["header"], r["std_field"]],
            ).fetchone()
            if row:
                existing += 1
                continue
            con.execute(
                "INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by) "
                "VALUES (?, ?, 'default', 1, 'seed', ?)",
                [r["header"], r["std_field"], actor],
            )
            inserted += 1
    return {"ok": True, "inserted": inserted, "existing": existing}


def _domain_field(std_field: str, domain: str) -> str | None:
    """Map a confirmed std_field onto a key present in ALIASES[domain]."""
    if std_field == "ignore":
        return None
    alias = ALIASES.get(domain) or {}
    if std_field in alias:
        return std_field
    for cand in _STD_TO_DOMAIN.get(std_field, []):
        if cand in alias:
            return cand
    return None


def _fetch_rules(business_domain: str | None = None) -> list[dict[str, Any]]:
    con = meta_conn()
    try:
        ensure_rule_dict_schema(con)
        if business_domain and business_domain not in ("default", "*"):
            rows = con.execute(
                """
                SELECT header, std_field, business_domain, hits, source, confirmed_by, created_at
                FROM rule_dict
                WHERE status='active' AND business_domain IN (?, 'default')
                ORDER BY hits DESC, created_at DESC, rule_id DESC
                """,
                [business_domain],
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT header, std_field, business_domain, hits, source, confirmed_by, created_at
                FROM rule_dict
                WHERE status='active'
                ORDER BY hits DESC, created_at DESC, rule_id DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def lookup_header(
    header: str,
    *,
    business_domain: str | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Best rule for a header (hits desc). Includes conflict flag when >1 non-ignore std_field."""
    rules = rules if rules is not None else _fetch_rules(business_domain)
    raw = str(header or "").strip()
    if not raw:
        return None
    nkey = _norm(raw)
    ckey = _canon_header(raw)

    exact: list[dict] = []
    fuzzy: list[dict] = []
    for r in rules:
        rh = str(r.get("header") or "").strip()
        if not rh:
            continue
        if rh == raw:
            exact.append(r)
        elif _norm(rh) == nkey or _canon_header(rh) == ckey:
            fuzzy.append(r)

    matched = exact or fuzzy
    if not matched:
        return None

    non_ignore = [r for r in matched if str(r.get("std_field") or "") != "ignore"]
    # Prefer non-ignore when ranking; ignore-only still wins if that's all we have
    ranked = non_ignore or matched
    best = ranked[0]
    distinct_fields = {str(r["std_field"]) for r in non_ignore}
    conflict = len(distinct_fields) > 1
    return {
        "header": raw,
        "std_field": str(best["std_field"]),
        "hits": int(best.get("hits") or 0),
        "source": "exact" if exact else "norm",
        "conflict": conflict,
        "candidates": [
            {"std_field": str(r["std_field"]), "hits": int(r.get("hits") or 0)} for r in matched[:5]
        ],
        "business_domain": best.get("business_domain"),
    }


def dict_prefill(
    headers: list[str],
    *,
    business_domain: str | None = None,
) -> tuple[dict[str, str], dict[str, dict], list[str]]:
    """Return (prefill, hit_meta, conflict_headers). Skip conflicted headers (04 §6.4)."""
    rules = _fetch_rules(business_domain)
    prefill: dict[str, str] = {}
    hit_meta: dict[str, dict] = {}
    conflicts: list[str] = []
    for h in headers:
        hit = lookup_header(h, business_domain=business_domain, rules=rules)
        if not hit:
            continue
        if hit["conflict"]:
            conflicts.append(h)
            hit_meta[h] = hit
            continue
        prefill[h] = hit["std_field"]
        hit_meta[h] = hit
    return prefill, hit_meta, conflicts


def apply_rule_overrides(
    columns: list[str],
    domain: str,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Merge rule_dict into column map: dict wins over ALIASES; skip conflicts / ignore."""
    mapping = dict(base or {})
    rules = _fetch_rules(domain)
    # Track which source cols already claimed
    used_cols = set(mapping.values())
    for col in columns:
        hit = lookup_header(col, business_domain=domain, rules=rules)
        if not hit or hit["conflict"]:
            continue
        std = hit["std_field"]
        if std == "ignore":
            continue
        target = _domain_field(std, domain)
        if not target:
            continue
        # Do not steal a column already assigned; do override target from weaker ALIASES
        if col in used_cols and mapping.get(target) != col:
            # column already mapped to another field — skip
            continue
        prev = mapping.get(target)
        if prev and prev != col and prev in columns:
            # replace previous ALIASES pick with confirmed dict header
            used_cols.discard(prev)
        mapping[target] = col
        used_cols.add(col)
    return mapping


def _rule_affected_rows(rule_id: int) -> int:
    """待处理影响行数：未确认字段待办 + 阻塞明细中同名表头的行数。"""
    con = meta_conn()
    try:
        row = con.execute(
            "SELECT header FROM rule_dict WHERE rule_id=?", [rule_id]
        ).fetchone()
        if not row:
            raise KeyError("rule not found")
        header = str(row["header"] or "")
        mp = con.execute(
            "SELECT COUNT(*) AS c FROM map_pending WHERE header=? AND status='pending'",
            [header],
        ).fetchone()["c"]
        sb = con.execute(
            "SELECT COUNT(*) AS c FROM staging_blocked WHERE header=?",
            [header],
        ).fetchone()["c"]
        return int(mp or 0) + int(sb or 0)
    finally:
        con.close()


def set_rule_status(
    *,
    rule_id: int,
    action: str,
    actor: str,
    dry_run: bool = False,
    note: str = "",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """启用/停用规则。变更前 dry_run 返回影响预演；真实变更写审计（仅追加）。"""
    action = (action or "").strip().lower()
    if action not in ("enable", "disable"):
        raise ValueError("action must be enable|disable")

    from app.services import idempotency as idem

    scope = "rule_dict_status"
    if idempotency_key and not dry_run:
        cached = idem.get(scope, idempotency_key)
        if cached:
            return {**cached, "idempotent": True, "idempotency_replay": True}

    con = meta_conn()
    try:
        ensure_rule_dict_schema(con)
        row = con.execute(
            """
            SELECT rule_id, header, std_field, business_domain, hits, status, created_at
            FROM rule_dict WHERE rule_id=?
            """,
            [rule_id],
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise KeyError("rule not found")

    d = dict(row)
    affected = _rule_affected_rows(rule_id)
    next_status = "active" if action == "enable" else "disabled"
    warning = "规则变更仅影响后续规整与映射命中；已写入业务库的历史行不会自动回刷。"
    preview = {
        "ok": True,
        "dry_run": True,
        "rule_id": rule_id,
        "header": d["header"],
        "std_field": d["std_field"],
        "business_domain": d["business_domain"],
        "current_status": d["status"],
        "next_status": next_status,
        "action": action,
        "affected_rows": affected,
        "rebuild_needed": False,
        "warning": warning,
    }
    if dry_run:
        return preview
    if d["status"] == next_status:
        raise RuntimeError(f"already_{next_status}")

    detail = json.dumps(
        {
            "rule_id": rule_id,
            "header": d["header"],
            "std_field": d["std_field"],
            "business_domain": d["business_domain"],
            "affected_rows": affected,
            "rebuild_needed": False,
        },
        ensure_ascii=False,
    )
    with meta_tx() as con:
        con.execute(
            """
            UPDATE rule_dict
            SET status=?, changed_by=?, updated_at=datetime('now')
            WHERE rule_id=?
            """,
            [next_status, actor, rule_id],
        )
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('rule_dict_status', ?, ?, ?, ?)
            """,
            [detail, action, (note or "")[:200] or warning[:200], actor],
        )
    out = {**preview, "dry_run": False}
    if idempotency_key:
        idem.put(scope, idempotency_key, out)
    return out


def list_rule_conflicts() -> dict[str, Any]:
    """同一表头在同一域下映射到多个不同标准字段 → 冲突（含停用项提示）。"""
    con = meta_conn()
    try:
        ensure_rule_dict_schema(con)
        rows = con.execute(
            """
            SELECT rule_id, header, std_field, business_domain, status
            FROM rule_dict
            ORDER BY header, business_domain
            """
        ).fetchall()
    finally:
        con.close()

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        key = (str(r["header"] or "").strip().lower(), str(r["business_domain"] or "default"))
        groups.setdefault(key, []).append(dict(r))

    conflicts: list[dict[str, Any]] = []
    for (_, domain), items in groups.items():
        non_ignore = [it for it in items if str(it.get("std_field") or "") != "ignore"]
        fields = {str(it["std_field"]) for it in non_ignore}
        if len(fields) > 1:
            conflicts.append(
                {
                    "header": items[0]["header"],
                    "business_domain": domain,
                    "fields": sorted(fields),
                    "rule_ids": [int(it["rule_id"]) for it in items],
                    "statuses": [str(it.get("status") or "active") for it in items],
                }
            )
    return {
        "ok": len(conflicts) == 0,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }
