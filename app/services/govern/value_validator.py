# -*- coding: utf-8 -*-
"""Value-domain checks for staging (roadmap §3 / P1-2)."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pandas as pd

from app.repositories import meta_tx

_NUM_RE = re.compile(r"^[\d,.\-\+eE]+$")

# T5 (LD-4, 2026-08-10)：台账非数字数量/单位清洗规则集（真实文件实测形态）
_QTY_FIELDS = (
    "stock_qty",
    "quota_qty",
    "min_qty",
    "opening_qty",
    "company_wh_qty",
    "asset_qty",
    "replace_cycle",
    "check_cycle",
    "asset_quota_qty",
)
_QTY_PLUS_RE = re.compile(r"^([-+]?\d+(?:\.\d+)?)\s*[+＋]\s*$")  # 50+ / 150+ / 20+
_QTY_SUFFIX_RE = re.compile(r"^([-+]?\d+(?:\.\d+)?)\s*([^\d\s+＋]+)$")  # 120对 / 1包 / 50米
_TEXT_NUM = {"一年一次": "1", "已取消，0": "0"}
_BLANK_TOKENS = {"无定额", "/", "-", "--"}


def _clean_qty_value(v: Any) -> Any:
    """T5.1: 单值清洗。返回规范值或原值；None/空保持原样（由校验决定是否拦截）。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return v
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return v
    if s in _TEXT_NUM:  # "一年一次"→1、"已取消，0"→0（源台账原文）
        return _TEXT_NUM[s]
    if s in _BLANK_TOKENS:  # "无定额"、"/"：合法的"无"标记 → 空
        return ""
    m = _QTY_PLUS_RE.match(s)
    if m:  # "50+" → 50（去 + 后缀，LD-4）
        return m.group(1)
    m = _QTY_SUFFIX_RE.match(s)
    if m:  # "120对" → 120（数量数值化；单位列原值保留，T5.3）
        return m.group(1)
    return v


def clean_ledger_qtys(df: pd.DataFrame, col_map: dict[str, str]) -> pd.DataFrame:
    """T5.2: 台账数量/单位清洗（normalize → resolve → clean → apply_checks 之间）。

    规范化 qty 类字段：去 "+" 后缀、去单位后缀、"已取消，0"→0、"一年一次"→1、
    "无定额"/"/"→空。其余不可解析值保持原样 → apply_checks 拦截（VALUE_RANGE），
    不静默置 NULL（LD-4 已锁定）。
    """
    df = df.copy()
    for field in _QTY_FIELDS:
        col = col_map.get(field)
        if not col or col not in df.columns:
            continue
        df[col] = df[col].map(_clean_qty_value)
    return df


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def ensure_value_rule_seed() -> int:
    """Seed a few active inventory checks if table empty of active rules."""
    seeds = [
        {
            "rule_id": "vr_inv_qty_pos",
            "domain": "inventory",
            "std_field": "stock_qty",
            "check_type": "numeric_positive",
            "params_json": "{}",
            "severity": "block",
            "status": "active",
        },
        {
            "rule_id": "vr_inv_name_req",
            "domain": "inventory",
            "std_field": "material_name",
            "check_type": "required",
            "params_json": "{}",
            "severity": "block",
            "status": "active",
        },
        {
            "rule_id": "vr_dem_qty_pos",
            "domain": "demand",
            "std_field": "quantity",
            "check_type": "numeric_positive",
            "params_json": "{}",
            "severity": "block",
            "status": "active",
        },
        # T5.1 (LD-4, 2026-08-10)：台账数量/周期字段校验种子（先 clean 后校验，
        # "50+"/"120对"等经 clean_ledger_qtys 规范化；其余不可解析值落 staging_blocked）
        {
            "rule_id": "vr_inv_opening_num",
            "domain": "inventory",
            "std_field": "opening_qty",
            "check_type": "numeric_positive",
            "params_json": "{}",
            "severity": "block",
            "status": "active",
        },
        {
            "rule_id": "vr_inv_min_num",
            "domain": "inventory",
            "std_field": "min_qty",
            "check_type": "numeric_positive",
            "params_json": "{}",
            "severity": "block",
            "status": "active",
        },
        {
            "rule_id": "vr_inv_quota_num",
            "domain": "inventory",
            "std_field": "quota_qty",
            "check_type": "numeric_positive",
            "params_json": "{}",
            "severity": "block",
            "status": "active",
        },
        {
            "rule_id": "vr_ast_qty_pos",
            "domain": "asset",
            "std_field": "asset_qty",
            "check_type": "numeric_positive",
            "params_json": "{}",
            "severity": "block",
            "status": "active",
        },
        {
            "rule_id": "vr_ast_check_cycle_num",
            "domain": "asset",
            "std_field": "check_cycle",
            "check_type": "numeric_positive",
            "params_json": "{}",
            "severity": "block",
            "status": "active",
        },
    ]
    n = 0
    with meta_tx() as con:
        for s in seeds:
            exists = con.execute(
                "SELECT 1 FROM value_rule WHERE rule_id=?", [s["rule_id"]]
            ).fetchone()
            if exists:
                continue
            con.execute(
                """
                INSERT INTO value_rule (
                    rule_id, domain, std_field, check_type, params_json, severity, status, confirmed_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'seed')
                """,
                [
                    s["rule_id"],
                    s["domain"],
                    s["std_field"],
                    s["check_type"],
                    s["params_json"],
                    s["severity"],
                    s["status"],
                ],
            )
            n += 1
    return n


def list_active_rules(domain: str) -> list[dict[str, Any]]:
    with meta_tx() as con:
        rows = con.execute(
            """
            SELECT * FROM value_rule
            WHERE domain=? AND status='active'
            ORDER BY created_at ASC
            """,
            [domain],
        ).fetchall()
    return [dict(r) for r in rows]


def list_value_rules(*, status: str | None = None, domain: str | None = None) -> dict:
    with meta_tx() as con:
        sql = "SELECT * FROM value_rule WHERE 1=1"
        args: list[Any] = []
        if status:
            sql += " AND status=?"
            args.append(status)
        if domain:
            sql += " AND domain=?"
            args.append(domain)
        sql += " ORDER BY created_at DESC"
        rows = con.execute(sql, args).fetchall()
    return {"total": len(rows), "items": [dict(r) for r in rows]}


def upsert_value_rule(
    *,
    rule_id: str | None,
    domain: str,
    std_field: str,
    check_type: str,
    params: dict | None = None,
    severity: str = "block",
    status: str = "proposed",
    actor: str = "",
) -> dict:
    rid = (rule_id or f"vr_{_sid(10)}").strip()
    with meta_tx() as con:
        exists = con.execute("SELECT rule_id FROM value_rule WHERE rule_id=?", [rid]).fetchone()
        blob = json.dumps(params or {}, ensure_ascii=False)
        if exists:
            con.execute(
                """
                UPDATE value_rule
                SET domain=?, std_field=?, check_type=?, params_json=?, severity=?, status=?,
                    confirmed_by=CASE WHEN ?='active' THEN ? ELSE confirmed_by END
                WHERE rule_id=?
                """,
                [domain, std_field, check_type, blob, severity, status, status, actor, rid],
            )
        else:
            con.execute(
                """
                INSERT INTO value_rule (
                    rule_id, domain, std_field, check_type, params_json, severity, status, confirmed_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [rid, domain, std_field, check_type, blob, severity, status, actor or None],
            )
    return {"ok": True, "rule_id": rid, "status": status}


def confirm_value_rule(rule_id: str, *, actor: str, decision: str = "accept") -> dict:
    decision = (decision or "accept").lower()
    with meta_tx() as con:
        row = con.execute("SELECT * FROM value_rule WHERE rule_id=?", [rule_id]).fetchone()
        if not row:
            raise KeyError("rule not found")
        new_status = "active" if decision in ("accept", "activate") else "disabled"
        con.execute(
            "UPDATE value_rule SET status=?, confirmed_by=? WHERE rule_id=?",
            [new_status, actor, rule_id],
        )
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('value_rule', ?, ?, '', ?)
            """,
            [rule_id[:200], decision, actor],
        )
    return {"ok": True, "rule_id": rule_id, "status": new_status, "actor": actor}


def _parse_num(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace(",", "").replace("，", "")
    if not s or not _NUM_RE.match(s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_blank(v: Any) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return True
    s = str(v).strip()
    return s == "" or s.lower() in {"nan", "none", "null", "-"}


def apply_checks(
    df: pd.DataFrame,
    *,
    domain: str,
    col_map: dict[str, str],
    rules: list[dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    """Return (clean_df, blocked_df, blocked_details). Warn rows stay in clean."""
    ensure_value_rule_seed()
    rules = rules if rules is not None else list_active_rules(domain)
    if df is None or df.empty or not rules:
        empty = df.iloc[0:0] if df is not None else pd.DataFrame()
        return df if df is not None else pd.DataFrame(), empty, []

    block_idx: set[int] = set()
    details: list[dict[str, Any]] = []

    for rule in rules:
        std = rule.get("std_field") or ""
        src = col_map.get(std)
        if not src or src not in df.columns:
            # required field unmapped → warn detail only (don't invent rows)
            if rule.get("check_type") == "required" and (rule.get("severity") or "block") == "block":
                details.append(
                    {
                        "source_row": None,
                        "header": src or std,
                        "reason_code": "REQUIRED_UNMAPPED",
                        "reason_detail": f"rule={rule.get('rule_id')} std={std} unmapped",
                        "raw_value": None,
                    }
                )
            continue
        ctype = (rule.get("check_type") or "").lower()
        severity = (rule.get("severity") or "block").lower()
        try:
            params = json.loads(rule.get("params_json") or "{}")
        except json.JSONDecodeError:
            params = {}

        for i, val in df[src].items():
            bad = False
            code = "OTHER"
            detail = ""
            if ctype == "required":
                if _is_blank(val):
                    bad, code, detail = True, "MISSING_COL", f"{std} required"
            elif ctype == "numeric_positive":
                if _is_blank(val):
                    # T5.3 (LD-4)：数值列允许空（空≠类型错误；必填由 required 规则负责）。
                    # 真实台账大量行无入库/定额记录，拦截会导致整批误伤。
                    continue
                num = _parse_num(val)
                if num is None:
                    bad, code, detail = True, "TYPE_ERROR", f"{std} not numeric"
                elif num < 0:
                    bad, code, detail = True, "VALUE_RANGE", f"{std}<0"
                elif num == 0 and params.get("allow_zero") is False:
                    bad, code, detail = True, "VALUE_RANGE", f"{std}==0"
            elif ctype == "max_length":
                mx = int(params.get("max") or 200)
                if not _is_blank(val) and len(str(val)) > mx:
                    bad, code, detail = True, "FORMAT_INVALID", f"len>{mx}"
            elif ctype == "regex":
                pat = params.get("pattern") or ""
                if pat and not _is_blank(val) and not re.search(pat, str(val)):
                    bad, code, detail = True, "FORMAT_INVALID", f"regex fail"
            elif ctype == "enum":
                vals = {str(x) for x in (params.get("values") or [])}
                if vals and not _is_blank(val) and str(val).strip() not in vals:
                    bad, code, detail = True, "VALUE_RANGE", "not in enum"
            if not bad:
                continue
            details.append(
                {
                    "source_row": int(i) if isinstance(i, (int, float)) else None,
                    "header": src,
                    "reason_code": code,
                    "reason_detail": detail,
                    "raw_value": (None if _is_blank(val) else str(val)[:200]),
                }
            )
            if severity == "block":
                block_idx.add(int(i) if isinstance(i, (int, float)) else i)

    if not block_idx:
        return df, df.iloc[0:0], details

    mask = df.index.isin(block_idx)
    blocked_df = df.loc[mask].copy()
    clean_df = df.loc[~mask].copy()
    return clean_df, blocked_df, details
