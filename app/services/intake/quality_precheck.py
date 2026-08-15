# -*- coding: utf-8 -*-
"""Step3 quality precheck — rule engine only (docs/03 Step3).

Full-scan on staging tabular frame. LLM interpretation is out of scope here.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pandas as pd

from app.repositories import meta_tx

# domain → required std fields (at least one of each group if nested list)
REQUIRED: dict[str, list[str | list[str]]] = {
    "inventory": [["material_code", "material_name"], "stock_qty"],
    "asset": [["asset_code", "asset_name"]],
    "demand": [["material_code", "material_name"], "quantity"],
    "stock_flow": [["material_code", "material_name"]],
}

PK_FIELDS: dict[str, list[str]] = {
    "inventory": ["material_code"],
    "asset": ["asset_code"],
    "demand": ["material_code", "demand_period"],
    "stock_flow": ["material_code", "material_name"],
}

QTY_FIELDS: dict[str, list[str]] = {
    "inventory": ["stock_qty", "quota_qty"],
    "asset": [],
    "demand": ["quantity", "unit_price", "total_price"],
    "stock_flow": ["qty_in", "qty_out"],
}

# 中危1 硬核验：金额列完整性。域 → 金额类 std 字段（任一映射即可）
MONEY_FIELDS: dict[str, list[str]] = {
    "inventory": ["unit_cost", "stock_value"],
    "demand": ["unit_price", "total_price"],
}
# 源表头命中金额语义但未被映射 → block（防静默丢钱）；源无金额列 → warn（口径提示）
MONEY_HEADER_HINTS = (
    "金额", "单价", "总价", "价格", "价税", "含税", "不含税", "金额(元)", "金额（元）",
    "unit price", "price", "amount", "cost",
)

_NUM_RE = re.compile(r"^[\d,.\-\+eE]+$")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _sid(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def _series(df: pd.DataFrame, col_map: dict[str, str], std: str) -> pd.Series | None:
    src = col_map.get(std)
    if not src or src not in df.columns:
        return None
    return df[src]


def _is_blank(v: Any) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return True
    s = str(v).strip()
    return s == "" or s.lower() in {"nan", "none", "null", "-"}


def _parse_number(v: Any) -> float | None:
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


def _money_check(
    df: pd.DataFrame,
    *,
    domain: str,
    col_map: dict[str, str],
) -> dict[str, Any]:
    """中危1 金额列提示（方案 B 已拍板：金额勾稽不硬核验，仅 FL6 数量勾稽）。

    - 域无金额字段 → ok；
    - 至少一个金额字段已映射且非全空 → ok；
    - 映射但全列空白 → warn（口径缺失）；
    - 源表头含金额语义但未映射 → block（防静默丢钱）；
    - 源无任何金额列 → ok（方案 B：不硬核验，仅提示口径）。
    不计入 counters/issue_total，避免破坏既有 ok/blocking 语义；由 gate 消费。
    """
    stds = MONEY_FIELDS.get(domain, [])
    if not stds:
        return {"std_fields": [], "mapped": True, "severity": "ok", "detail": ""}
    mapped = [s for s in stds if s in col_map and col_map[s] in df.columns]
    if mapped:
        ser = df[col_map[mapped[0]]]
        if len(ser) and bool(ser.map(_is_blank).all()):
            return {
                "std_fields": stds,
                "mapped": False,
                "severity": "warn",
                "detail": f"{mapped[0]} 已映射但全列空白",
            }
        return {"std_fields": stds, "mapped": True, "severity": "ok", "detail": ""}
    hits = [c for c in df.columns if any(h in str(c) for h in MONEY_HEADER_HINTS)]
    if hits:
        return {
            "std_fields": stds,
            "mapped": False,
            "severity": "block",
            "detail": f"源表头疑似金额但未映射：{hits[:5]}",
        }
    return {
        "std_fields": stds,
        "mapped": False,
        "severity": "ok",
        "detail": "源数据无金额列：金额勾稽不硬核验（方案 B，仅 FL6 数量勾稽）",
    }


def run_quality_precheck(
    df: pd.DataFrame,
    *,
    domain: str,
    col_map: dict[str, str] | None = None,
    sample_limit: int = 20,
) -> dict[str, Any]:
    """Return quality report; does not mutate df / biz DB."""
    col_map = col_map or {}
    n = int(len(df))
    issues: list[dict[str, Any]] = []
    counters: dict[str, int] = {
        "missing_required": 0,
        "duplicate_pk": 0,
        "qty_non_numeric": 0,
        "qty_negative": 0,
        "qty_year_like": 0,
        "empty_rows": 0,
    }

    if n == 0:
        return {
            "step": "quality_precheck",
            "source": "rule",
            "domain": domain,
            "row_count": 0,
            "ok": True,
            "severity": True,
            "issue_counts": counters,
            "issues_sample": [],
            "suggested_dedup": PK_FIELDS.get(domain, []),
            "required_fields": REQUIRED.get(domain, []),
            "mapped_fields": list(col_map.keys()),
            "money": {
                "std_fields": MONEY_FIELDS.get(domain, []),
                "mapped": True,
                "severity": "ok",
                "detail": "空表",
            },
            "hint": "空表；无质量问题可报",
        }

    # empty rows (all mapped cols blank)
    mapped_cols = [c for c in col_map.values() if c in df.columns]
    if mapped_cols:
        empty_mask = df[mapped_cols].apply(lambda r: all(_is_blank(x) for x in r), axis=1)
        empty_idx = df.index[empty_mask].tolist()
        counters["empty_rows"] = len(empty_idx)
        for i in empty_idx[:sample_limit]:
            issues.append({"code": "EMPTY_ROW", "row": int(i), "detail": "all mapped cells blank"})

    # required fields
    for req in REQUIRED.get(domain, []):
        if isinstance(req, list):
            present = [f for f in req if f in col_map and col_map[f] in df.columns]
            if not present:
                counters["missing_required"] += n
                issues.append(
                    {
                        "code": "REQUIRED_UNMAPPED",
                        "row": None,
                        "fields": req,
                        "detail": f"none of {req} mapped",
                    }
                )
                continue
            # row missing if ALL alternatives blank
            masks = []
            for f in present:
                ser = _series(df, col_map, f)
                assert ser is not None
                masks.append(ser.map(_is_blank))
            miss = masks[0]
            for m in masks[1:]:
                miss = miss & m
            miss_idx = df.index[miss].tolist()
            counters["missing_required"] += len(miss_idx)
            for i in miss_idx[:sample_limit]:
                issues.append(
                    {
                        "code": "MISSING_REQUIRED",
                        "row": int(i),
                        "fields": present,
                        "detail": "required group blank",
                    }
                )
        else:
            if req not in col_map or col_map[req] not in df.columns:
                counters["missing_required"] += n
                issues.append(
                    {
                        "code": "REQUIRED_UNMAPPED",
                        "row": None,
                        "fields": [req],
                        "detail": f"{req} not mapped",
                    }
                )
                continue
            ser = _series(df, col_map, req)
            assert ser is not None
            miss_idx = df.index[ser.map(_is_blank)].tolist()
            counters["missing_required"] += len(miss_idx)
            for i in miss_idx[:sample_limit]:
                issues.append(
                    {
                        "code": "MISSING_REQUIRED",
                        "row": int(i),
                        "fields": [req],
                        "detail": f"{req} blank",
                    }
                )

    # duplicate PK
    pk = [f for f in PK_FIELDS.get(domain, []) if f in col_map and col_map[f] in df.columns]
    suggested_dedup = pk or [f for f in ["material_code", "asset_code"] if f in col_map]
    if pk:
        parts = []
        for f in pk:
            ser = _series(df, col_map, f)
            assert ser is not None
            parts.append(ser.map(lambda x: "" if _is_blank(x) else str(x).strip()))
        key = parts[0]
        for p in parts[1:]:
            key = key + "|" + p
        # ignore blank keys
        nonempty = key.map(lambda s: bool(s) and s != "|".join([""] * len(pk)))
        dup_mask = key.duplicated(keep=False) & nonempty
        dup_idx = df.index[dup_mask].tolist()
        counters["duplicate_pk"] = int(dup_mask.sum())
        # unique duplicate key count
        dup_keys = key[dup_mask].value_counts().head(sample_limit)
        for k, cnt in dup_keys.items():
            issues.append(
                {
                    "code": "DUPLICATE_PK",
                    "row": None,
                    "fields": pk,
                    "detail": f"key={k} count={int(cnt)}",
                }
            )

    # quantity anomalies
    for qf in QTY_FIELDS.get(domain, []):
        if qf not in col_map or col_map[qf] not in df.columns:
            continue
        ser = _series(df, col_map, qf)
        assert ser is not None
        for i, raw in ser.items():
            if _is_blank(raw):
                continue
            s = str(raw).strip()
            if _YEAR_RE.match(s.replace(".0", "")):
                counters["qty_year_like"] += 1
                if counters["qty_year_like"] <= sample_limit:
                    issues.append(
                        {
                            "code": "QTY_YEAR_LIKE",
                            "row": int(i),
                            "fields": [qf],
                            "detail": f"value={s}",
                        }
                    )
                continue
            num = _parse_number(raw)
            if num is None:
                counters["qty_non_numeric"] += 1
                if counters["qty_non_numeric"] <= sample_limit:
                    issues.append(
                        {
                            "code": "QTY_NON_NUMERIC",
                            "row": int(i),
                            "fields": [qf],
                            "detail": f"value={s[:40]}",
                        }
                    )
            elif num < 0:
                counters["qty_negative"] += 1
                if counters["qty_negative"] <= sample_limit:
                    issues.append(
                        {
                            "code": "QTY_NEGATIVE",
                            "row": int(i),
                            "fields": [qf],
                            "detail": f"value={num}",
                        }
                    )

    issue_total = sum(counters.values())
    # severity: blocking on required-field gaps only. Year-like qty (19xx/20xx) is a
    # suspect-value warning — stock 2000/2024 are legal quantities and blocking them
    # deadlocks real ledgers (维护材料 sheet qty=2000 blocked GATE_BLOCKED:QUALITY_BLOCKING).
    blocking = counters["missing_required"] > 0
    return {
        "step": "quality_precheck",
        "source": "rule",
        "domain": domain,
        "row_count": n,
        "ok": issue_total == 0,
        "blocking": blocking,
        "issue_counts": counters,
        "issue_total": issue_total,
        "issues_sample": issues[: sample_limit * 2],
        "suggested_dedup": suggested_dedup,
        "required_fields": REQUIRED.get(domain, []),
        "mapped_fields": list(col_map.keys()),
        "money": _money_check(df, domain=domain, col_map=col_map),
        "hint": (
            "质量预检为规则全量结果；blocking=true 时建议先治理再 confirm。"
            "LLM 解读未启用。"
        ),
    }


def save_quality_report(file_id: str, payload: dict[str, Any]) -> str:
    report_id = _sid()
    with meta_tx() as con:
        con.execute(
            "DELETE FROM intake_report WHERE file_id=? AND report_type='quality_precheck'",
            [file_id],
        )
        con.execute(
            """
            INSERT INTO intake_report (report_id, file_id, report_type, payload_json)
            VALUES (?, ?, 'quality_precheck', ?)
            """,
            [report_id, file_id, json.dumps(payload, ensure_ascii=False, default=str)],
        )
    return report_id


def get_quality_report(file_id: str) -> dict[str, Any] | None:
    with meta_tx() as con:
        row = con.execute(
            """
            SELECT report_id, file_id, report_type, payload_json, created_at
            FROM intake_report
            WHERE file_id=? AND report_type='quality_precheck'
            ORDER BY created_at DESC LIMIT 1
            """,
            [file_id],
        ).fetchone()
    if not row:
        return None
    return {
        "report_id": row["report_id"],
        "file_id": row["file_id"],
        "report_type": row["report_type"],
        "created_at": row["created_at"],
        "quality": json.loads(row["payload_json"] or "{}"),
    }
