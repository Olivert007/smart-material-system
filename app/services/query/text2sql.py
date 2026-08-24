# -*- coding: utf-8 -*-
"""Text2SQL via AskEngine + AST guard + readonly exec."""
from __future__ import annotations

from app import config
from app.repositories import biz_conn, meta_tx
from app.services.jsonutil import json_safe
from app.services.llm.model_client import chat
from app.services.query.ask_engine import get_ask_engine
from app.services.query.ask_insights import (
    degraded_suggested_examples,
    empty_result_insight,
)
from app.services.query.legacy_text2sql_engine import _guard_error_zh
from app.services.sql_guard import validate_readonly_sql

SCHEMA_ZH = {
    "dim_material": {
        "material_id": "物料内部ID",
        "material_code": "物资编码",
        "material_name": "物资名称",
        "spec": "规格型号",
        "unit": "计量单位",
        "category": "物资大类",
    },
    "fact_inventory": {
        "inventory_id": "库存记录ID",
        "material_id": "物料ID",
        "region": "区域",
        "category": "物资类别",
        "stock_qty": "现有库存数量",
        "quota_qty": "定额数量",
        "unit": "计量单位",
        "location": "存放位置",
        "custodian": "保管人",
        "source_release_id": "发布ID",
    },
    "fact_asset": {
        "asset_code": "资产编码",
        "asset_name": "资产名称",
        "company": "公司",
        "location": "位置",
        "status": "状态",
    },
    "fact_demand": {
        "demand_id": "需求ID",
        "material_id": "物料ID",
        "demand_period": "需求期次",
        "quantity": "数量",
        "unit_price": "单价",
        "total_price": "合价",
    },
    "fact_stock_flow": {
        "flow_id": "流水ID",
        "material_id": "物料ID",
        "flow_type": "流向（IN入库/OUT出库）",
        "flow_date": "流水日期",
        "quantity": "数量",
        "unit": "计量单位",
        "person": "经办人",
        "purpose": "用途",
        "remark": "备注",
        "parse_level": "解析层级",
        "parse_source": "解析来源",
        "source_file": "来源文件",
        "source_sheet": "来源工作表",
        "source_row": "来源行号",
        "source_segment": "来源分段",
        "source_release_id": "发布ID",
    },
    "fact_quota_adjust": {
        "quota_id": "定额调整ID",
        "material_id": "物料ID",
        "adjust_type": "调整类型",
        "material_code": "物资编码",
        "material_name": "物资名称",
        "installed_qty": "装机数量",
        "accident_quota": "事故储备定额",
        "reserve_quota": "战备定额",
        "verified_quota": "核定额",
        "device_name": "装置名称",
        "reason": "调整原因",
        "delete_flag": "删除标记",
        "source_file": "来源文件",
        "source_release_id": "发布ID",
    },
}


def schema_summary() -> str:
    con = biz_conn()
    try:
        df = con.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='main'
            ORDER BY table_name, ordinal_position
            """
        ).fetchdf()
    finally:
        con.close()
    lines: list[str] = []
    cur = None
    for _, r in df.iterrows():
        if r["table_name"] != cur:
            if cur:
                lines.append("")
            cur = r["table_name"]
            lines.append(f"表 {cur}:")
        zh = SCHEMA_ZH.get(r["table_name"], {}).get(r["column_name"], "")
        lines.append(f"  - {r['column_name']} ({r['data_type']}){f'，{zh}' if zh else ''}")
    return "\n".join(lines)


def ask(question: str) -> dict:
    """问数入口：执行查询并把结果（含 SQL）写入审计日志（ask_log）。

    页面不再直接展示 SQL；排查走审计日志（docs optv2 问数助手 §7 后续调整）。
    """
    res = _ask(question)
    _audit_ask(res)
    return res


def _audit_ask(res: dict) -> None:
    """把问数请求/结果（含 SQL）落审计日志；失败不影响回答本身。"""
    try:
        with meta_tx() as con:
            con.execute(
                """
                INSERT INTO ask_log (
                    question, sql, source, metric_id, ok, degraded,
                    model_state, error, latency_ms, rows
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (res.get("question") or "")[:300],
                    (res.get("sql") or "")[:4000] or None,
                    res.get("source"),
                    res.get("metric_id"),
                    1 if res.get("ok") else 0,
                    1 if res.get("degraded") else 0,
                    res.get("model_state"),
                    (res.get("error") or "")[:500] or None,
                    res.get("latency_ms"),
                    res.get("rows"),
                ),
            )
    except Exception:
        # 审计失败不阻断问数
        pass


def _ask(question: str) -> dict:
    q = (question or "").strip()
    if not q:
        return {"ok": False, "error": "问题为空，请重新输入", "model_state": "not_attempted"}

    # ① Metric template first (docs/08 §5) — no LLM when unique active hit
    from app.services import metrics as metrics_svc

    matched = metrics_svc.match_metrics(q)
    best = matched.get("best")
    if matched.get("conflict"):
        return {
            "question": q,
            "ok": False,
            "error": "指标口径冲突，请到指标字典确认后再问",
            "code": "METRIC_CONFLICT",
            "model_state": "metric_conflict",
            "model_request_attempted": False,
            "model_invoked": False,
            "output_available": False,
            "metric_match": matched,
            "answer": "口径冲突：多个指标同义命中，请到指标字典确认后再问。",
            "hint": "C4：冲突不静默选",
        }
    if best:
        mid = best["metric_id"]
        status = best.get("status")
        if mid.startswith("FLOW_") and status != "active":
            return {
                "question": q,
                "ok": False,
                "error": "流水指标处于草稿状态，暂不按口径模板作答",
                "code": "FLOW_QUALITY_GATE",
                "model_state": "metric_draft_blocked",
                "model_request_attempted": False,
                "model_invoked": False,
                "output_available": False,
                "metric_match": matched,
                "metric_id": mid,
                "sql": best.get("definition_sql"),
                "answer": "流水质量未达标，流水类指标保持草稿状态，暂不按口径模板作答。",
                "hint": "见 12/08 门禁；可先问库存/需求/资产类指标",
            }
        if status == "active":
            try:
                ev = metrics_svc.evaluate_metric(mid)
            except Exception as e:
                return {
                    "question": q,
                    "ok": False,
                    "error": str(e),
                    "metric_id": mid,
                    "model_state": "metric_eval_failed",
                    "model_request_attempted": False,
                    "model_invoked": False,
                }
            sql = best.get("definition_sql") or ""
            val = ev.get("value")
            unit = ev.get("unit") or ""
            # 空表聚合（SUM/COUNT 等）会返回 NULL；单位不统一等口径下指标
            # definition_sql 也返回 NULL（不可加总）。此时展示「—」，避免误读为 0。
            if val is None:
                answer = f"{best.get('metric_name')} = —{(' ' + unit) if unit else ''}"
                insight = empty_result_insight(
                    question=q,
                    sql=sql,
                    source="metric_template",
                    metric_id=mid,
                )
            else:
                answer = f"{best.get('metric_name')} = {val}{(' ' + unit) if unit else ''}"
                insight = None
            payload = {
                "question": q,
                "ok": True,
                "sql": sql,
                "rows": 1,
                "columns": ["v"],
                "data": [{"v": val}],
                "answer": answer,
                "metric_id": mid,
                "metric_name": best.get("metric_name"),
                "metric_version": ev.get("version"),
                "unit": unit or None,
                "metric_match": matched,
                "source": "metric_template",
                "data_scope": "available_candidate",
                "model_state": "metric_template_hit",
                "model_request_attempted": False,
                "model_invoked": False,
                "output_available": True,
                "model": None,
                "latency_ms": 0,
                "hint": "指标模板优先：未调用生成模型",
            }
            if insight:
                payload.update(insight)
            return payload

    engine = get_ask_engine()
    gen = engine.generate_sql(q, metric_match=matched)
    base = {
        "question": q,
        "model": gen.model,
        "model_request_attempted": gen.model_request_attempted,
        "model_invoked": gen.model_invoked,
        "output_available": gen.output_available,
        "model_state": gen.model_state,
        "fallback_reason": gen.fallback_reason,
        "latency_ms": gen.latency_ms,
        "source": gen.source,
        "engine_state": gen.engine_state,
        "data_scope": "available_candidate",
        "metric_match": matched,
    }
    if gen.engine_fallback:
        base["engine_fallback"] = True
        base["hint"] = "Vanna 引擎未命中，已回退基础问数"
    if not gen.ok:
        degraded = str(gen.model_state or "") in {
            "local_model_unavailable",
            "circuit_open",
            "llm_invocation_failed",
            "model_unavailable",
        }
        return {
            **base,
            "ok": False,
            "sql": gen.sql,
            "error": gen.error or "model unavailable",
            "code": gen.code,
            "answer": None,
            "degraded": degraded,
            "hint": (
                "Vanna 引擎未命中，已回退基础问数。"
                + (
                    " 本地模型不可用：复杂问数暂不可用。指标模板类问题仍可回答"
                    "（例如：库存总量是多少、库存表有多少行、资产台数有多少）。"
                    "数据成果浏览与导出不受影响。"
                    if degraded
                    else ""
                )
            )
            if (degraded or gen.engine_fallback)
            else None,
            "available_capabilities": (
                ["metric_template_ask", "browse", "export", "govern", "trace"]
                if degraded
                else None
            ),
            "suggested_examples": degraded_suggested_examples() if degraded else None,
        }

    guard = validate_readonly_sql(gen.sql or "")
    if not guard.ok:
        return {
            **base,
            "ok": False,
            "sql": gen.sql,
            "error": _guard_error_zh(guard),
            "code": guard.code,
            "answer": None,
        }

    con = biz_conn()
    try:
        df = con.execute(guard.sql).fetchdf()
    except Exception as e:
        return {**base, "ok": False, "sql": guard.sql, "error": "查询执行失败，请换个问法", "answer": None}
    finally:
        con.close()

    brief = {c: df[c].head(8).tolist() for c in list(df.columns)[:5]}
    summary = chat(
        role="big",
        task_type="ask_summary",
        messages=[
            {"role": "system", "content": "你是仓库管理助手。只用中文一句话回答，不要思考过程。"},
            {
                "role": "user",
                "content": f"问题：{q}\nSQL：{guard.sql}\n结果预览：{brief}\n一句话回答：",
            },
        ],
        temperature=0.2,
        max_tokens=120,
    )
    answer = summary.text.strip() if summary.ok else None
    if answer and ("thinking" in answer.lower() or "思考" in answer[:20]):
        # keep last non-empty line as answer heuristic
        lines = [ln.strip() for ln in answer.splitlines() if ln.strip()]
        answer = lines[-1] if lines else answer
    total_rows = int(len(df))
    row_cap = config.QUERY_ROW_LIMIT
    payload = {
        **base,
        "ok": True,
        "sql": guard.sql,
        "rows": total_rows,
        "total_rows": total_rows,
        "truncated": total_rows > row_cap,
        "columns": list(df.columns),
        "data": json_safe(df.head(row_cap).to_dict(orient="records")),
        "answer": answer,
        "summary_model_state": summary.model_state,
    }
    if total_rows == 0:
        payload.update(
            empty_result_insight(question=q, sql=guard.sql, source="llm_text2sql")
        )
    return payload
