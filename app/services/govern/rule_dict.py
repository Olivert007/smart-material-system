# -*- coding: utf-8 -*-
"""rule_dict self-learning lookups (docs/04 §6) — read path for map-suggest / resolve_columns."""
from __future__ import annotations

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


def ensure_seed_rules(*, actor: str = "system:seed") -> dict:
    """幂等写入 default 域种子规则（INSERT OR IGNORE 语义）。"""
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
        if business_domain and business_domain not in ("default", "*"):
            rows = con.execute(
                """
                SELECT header, std_field, business_domain, hits, source, confirmed_by, created_at
                FROM rule_dict
                WHERE business_domain IN (?, 'default')
                ORDER BY hits DESC, created_at DESC, rule_id DESC
                """,
                [business_domain],
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT header, std_field, business_domain, hits, source, confirmed_by, created_at
                FROM rule_dict
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
