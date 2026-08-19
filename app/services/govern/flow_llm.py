# -*- coding: utf-8 -*-
"""Phase B: LLM structured suggestions for flow_pending (docs/12 B1–B2).

Writes ONLY meta.flow_pending.suggested_json — never DuckDB / fact_stock_flow.
Disabled via FLOW_LLM_ENABLED=0 so A-规则 path stays complete.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app import config
from app.repositories import meta_conn, meta_tx
from app.services.model_client import LlmResult, parse_json_object
from app.services.policy_router import route_chat

_YEAR_QTY = re.compile(r"^(?:19|20)\d{2}(?:\.0+)?$")

_SYSTEM = """你是物资出入库自由文本解析助手。只输出一个 JSON 对象，不要 Markdown。
字段：
{
  "flow_type": "IN" 或 "OUT",
  "flow_date": "YYYY-MM-DD" 或 null,
  "quantity": 数字或 null,
  "unit": 字符串或 null,
  "person": 字符串或 null（多人用分号连接，不要拆成多条）,
  "purpose": 字符串或 null,
  "remark": 原文本摘要,
  "parse_level": "L1"|"L2"|"L3",
  "confidence": 0到1的小数,
  "flags": 字符串数组
}
硬性规则：
1) 禁止把四位年份（如 2023、2023年）当作 quantity。
2) 「借用」→ flow_type=OUT，flags 含 BORROW。
3) 字段不全用 L2；无法结构化用 L3 且 quantity/flow_date 可为 null。
4) 日期只进 flow_date，不要把日期数字写入 quantity。
5) 若原文无明确数量，但提示了「单列数量」，可借用该数量，flags 加 qty_from_column。
6) 原文为「已使用」「/」「无」等 → L3，quantity=null。
"""


def _looks_year_qty(q: Any) -> bool:
    if q is None:
        return False
    try:
        f = float(q)
    except (TypeError, ValueError):
        return False
    if f != int(f):
        return False
    yi = int(f)
    return 1900 <= yi <= 2100


def validate_flow_suggestion(result: LlmResult) -> tuple[bool, list[str]]:
    issues: list[str] = []
    obj = parse_json_object(result.text or "")
    if not obj:
        return False, ["json_parse_failed"]
    ft = str(obj.get("flow_type") or "").upper()
    if ft not in ("IN", "OUT"):
        issues.append("bad_flow_type")
    qty = obj.get("quantity")
    if _looks_year_qty(qty) or (isinstance(qty, str) and _YEAR_QTY.match(qty.strip())):
        issues.append("year_as_quantity")
    level = str(obj.get("parse_level") or "").upper()
    if level not in ("L1", "L2", "L3"):
        issues.append("bad_parse_level")
    try:
        conf = float(obj.get("confidence")) if obj.get("confidence") is not None else 0.0
    except (TypeError, ValueError):
        conf = 0.0
        issues.append("bad_confidence")
    if conf < config.FLOW_LLM_CONFIDENCE_MIN and level == "L1":
        issues.append("low_confidence_for_l1")
    if conf < 0.35:
        issues.append("low_confidence")
    # Hard fails only: unusable JSON structure / year-as-qty / bad type.
    # Low confidence is soft — escalate may still rewrite; normalize demotes L1→L2.
    hard = [i for i in issues if i in ("json_parse_failed", "bad_flow_type", "year_as_quantity")]
    return (len(hard) == 0), issues


def _normalize_suggestion(
    obj: dict[str, Any],
    *,
    flow_type: str,
    text_raw: str,
    rule_suggested: dict[str, Any],
    role: str,
) -> dict[str, Any]:
    ft = str(obj.get("flow_type") or flow_type or "OUT").upper()
    if ft not in ("IN", "OUT"):
        ft = flow_type or "OUT"
    qty = obj.get("quantity")
    if _looks_year_qty(qty):
        qty = None
    # P2-like: borrow column/rule qty when LLM left quantity empty (not year)
    if qty is None:
        rq = rule_suggested.get("quantity")
        if rq is not None and not _looks_year_qty(rq):
            try:
                qty = float(rq)
                obj_flags = obj.get("flags") if isinstance(obj.get("flags"), list) else []
                obj_flags = list(obj_flags) + ["qty_from_column"]
                obj["flags"] = obj_flags
            except (TypeError, ValueError):
                pass
    try:
        conf = float(obj.get("confidence")) if obj.get("confidence") is not None else 0.5
    except (TypeError, ValueError):
        conf = 0.5
    level = str(obj.get("parse_level") or "L2").upper()
    if level not in ("L1", "L2", "L3"):
        level = "L2"
    if conf < config.FLOW_LLM_CONFIDENCE_MIN and level == "L1":
        level = "L2"
    if qty is None and level == "L1":
        level = "L2"
    flags = obj.get("flags") if isinstance(obj.get("flags"), list) else []
    flags = [str(x) for x in flags]
    if "借用" in (text_raw or "") and "BORROW" not in flags:
        flags.append("BORROW")
        ft = "OUT"
    out = {
        **rule_suggested,
        "flow_type": ft,
        "flow_date": obj.get("flow_date") or None,
        "quantity": qty,
        "unit": obj.get("unit") or rule_suggested.get("unit"),
        "person": obj.get("person") or None,
        "purpose": obj.get("purpose") or None,
        "remark": obj.get("remark") or text_raw,
        "parse_level": level,
        "parse_source": "llm",
        "confidence": conf,
        "flags": flags,
        "_rule": {k: v for k, v in rule_suggested.items() if not str(k).startswith("_")},
        "_llm_role": role,
    }
    return out


def suggest_one(pending_id: str, *, force_role: str | None = None) -> dict[str, Any]:
    """Run PolicyRouter for one pending row; update suggested_json only."""
    if not config.FLOW_LLM_ENABLED:
        return {"ok": False, "skipped": True, "reason": "FLOW_LLM_DISABLED", "pending_id": pending_id}

    with meta_tx() as con:
        row = con.execute(
            "SELECT * FROM flow_pending WHERE pending_id=?", [pending_id]
        ).fetchone()
        if not row:
            raise KeyError(pending_id)
        row = dict(row)
        if row.get("status") != "pending":
            return {
                "ok": True,
                "skipped": True,
                "reason": f"status={row.get('status')}",
                "pending_id": pending_id,
            }
        con.execute(
            """
            UPDATE flow_pending
            SET llm_state='queued', updated_at=datetime('now')
            WHERE pending_id=?
            """,
            [pending_id],
        )

    try:
        rule_suggested: dict[str, Any] = {}
        try:
            rule_suggested = json.loads(row.get("suggested_json") or "{}")
            if not isinstance(rule_suggested, dict):
                rule_suggested = {}
        except json.JSONDecodeError:
            rule_suggested = {}

        user = (
            f"flow_type 提示: {row.get('flow_type') or ''}\n"
            f"source_sheet: {row.get('source_sheet') or ''}\n"
            f"单列数量(无文本数量时可借用，禁止把年份当数量): {rule_suggested.get('quantity')}\n"
            f"单列单位: {rule_suggested.get('unit')}\n"
            f"原文: {row.get('text_raw') or ''}\n"
            f"规则初稿(可参考勿盲从): {json.dumps(rule_suggested, ensure_ascii=False)[:600]}"
        )
        routed = route_chat(
            task_type="flow_parse_suggest",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            validate=validate_flow_suggestion,
            force_role=force_role,
        )
        if not routed.ok:
            with meta_tx() as con:
                con.execute(
                    """
                    UPDATE flow_pending
                    SET llm_state='failed', llm_role=?, llm_error=?, updated_at=datetime('now')
                    WHERE pending_id=?
                    """,
                    [
                        routed.role_used,
                        (",".join(routed.issues) or routed.result.error or "failed")[:500],
                        pending_id,
                    ],
                )
            return {
                "ok": False,
                "pending_id": pending_id,
                "mode": routed.mode,
                "role": routed.role_used,
                "issues": routed.issues,
                "attempts": routed.attempts,
            }

        obj = parse_json_object(routed.result.text or "") or {}
        merged = _normalize_suggestion(
            obj,
            flow_type=str(row.get("flow_type") or "OUT"),
            text_raw=str(row.get("text_raw") or ""),
            rule_suggested=rule_suggested,
            role=routed.role_used,
        )
        with meta_tx() as con:
            con.execute(
                """
                UPDATE flow_pending
                SET suggested_json=?, parse_level=?, llm_state='done', llm_role=?,
                    llm_error=NULL, updated_at=datetime('now')
                WHERE pending_id=? AND status='pending'
                """,
                [
                    json.dumps(merged, ensure_ascii=False, default=str),
                    merged.get("parse_level"),
                    routed.role_used,
                    pending_id,
                ],
            )
        return {
            "ok": True,
            "pending_id": pending_id,
            "mode": routed.mode,
            "role": routed.role_used,
            "parse_level": merged.get("parse_level"),
            "confidence": merged.get("confidence"),
            "suggestion": {
                k: merged.get(k)
                for k in (
                    "flow_type",
                    "flow_date",
                    "quantity",
                    "unit",
                    "person",
                    "purpose",
                    "parse_level",
                    "parse_source",
                    "confidence",
                    "flags",
                )
            },
            "attempts": routed.attempts,
        }
    except Exception as e:
        with meta_tx() as con:
            con.execute(
                """
                UPDATE flow_pending
                SET llm_state='failed', llm_error=?, updated_at=datetime('now')
                WHERE pending_id=?
                """,
                [str(e)[:500], pending_id],
            )
        return {"ok": False, "pending_id": pending_id, "error": str(e)}


def process_pending_batch(
    *,
    limit: int | None = None,
    force_role: str | None = None,
) -> dict[str, Any]:
    """Worker/API entry: suggest for pending rows with llm_state in (none,failed)."""
    if not config.FLOW_LLM_ENABLED:
        return {"ok": True, "skipped": True, "reason": "FLOW_LLM_DISABLED", "processed": 0}

    limit = max(1, min(int(limit or config.FLOW_LLM_BATCH), 50))
    con = meta_conn()
    try:
        rows = con.execute(
            """
            SELECT pending_id FROM flow_pending
            WHERE status='pending' AND COALESCE(llm_state,'none') IN ('none','failed')
            ORDER BY created_at ASC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
    finally:
        con.close()

    results = []
    for r in rows:
        results.append(suggest_one(r["pending_id"], force_role=force_role))
    ok_n = sum(1 for x in results if x.get("ok") and not x.get("skipped"))
    return {
        "ok": True,
        "processed": len(results),
        "succeeded": ok_n,
        "failed": sum(1 for x in results if not x.get("ok") and not x.get("skipped")),
        "skipped": sum(1 for x in results if x.get("skipped")),
        "items": results,
    }
