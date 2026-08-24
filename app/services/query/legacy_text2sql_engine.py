# -*- coding: utf-8 -*-
"""Legacy NL2SQL engine: big model + optional repair pass."""
from __future__ import annotations

import re

from app.services.llm.model_client import chat
from app.services.query.ask_engine import AskEngineResult
from app.services.sql_guard import validate_readonly_sql

_GUARD_ERROR_ZH = {
    "SQL_EMPTY": "生成的查询为空，请换个问法",
    "SQL_PARSE_ERROR": "查询语句无法解析，请换个问法",
    "SQL_MULTI_STATEMENT": "查询包含多条语句，仅允许单条只读查询",
    "SQL_FORBIDDEN": "查询包含受限操作，仅允许只读查询",
    "SQL_NOT_SELECT": "查询不是只读查询，仅允许查询数据",
    "SQL_FORBIDDEN_FN": "查询使用了受限函数，仅允许常规统计查询",
}


def _guard_error_zh(guard) -> str:
    return _GUARD_ERROR_ZH.get(guard.code) or f"查询未通过安全校验（{guard.code}）"


def extract_sql(text: str) -> str:
    raw = text or ""
    if "</think>" in raw:
        raw = raw.split("</think>", 1)[-1]
    raw = re.sub(r"```(?:sql)?", "", raw, flags=re.I).strip()
    matches = list(
        re.finditer(
            r"(?is)\b((?:with|select)\b[\s\S]*?)(?:;|\Z)",
            raw,
        )
    )
    for m in reversed(matches):
        cand = m.group(1).strip()
        if re.search(r"(?i)\b(from|count|with)\b", cand) and not re.search(
            r"(?i)\b(explanation|thinking|requirements?|I'll|don't)\b", cand
        ):
            cand = re.split(r"\n\s*\n", cand)[0].strip()
            return cand.rstrip(";").strip()
    for line in raw.splitlines():
        s = line.strip()
        if re.match(r"(?i)^(with|select)\b", s) and re.search(r"(?i)\b(from|count)\b", s):
            return s.rstrip(";").strip()
    return raw.rstrip(";").strip()


class LegacyText2SqlEngine:
    """Stage-1 text2sql via local big model."""

    def generate_sql(self, question: str, *, metric_match: dict | None = None) -> AskEngineResult:
        from app.services.query.text2sql import schema_summary

        q = (question or "").strip()
        schema = schema_summary()
        sys_msg = (
            "你是物资管理系统的 DuckDB 专家。根据表结构生成一条只读 SQL。\n"
            f"{schema}\n\n"
            "硬性要求：\n"
            "1. 最终输出只能是一条 SELECT/WITH，禁止解释、禁止 markdown、禁止思考过程。\n"
            "2. 中文条件用 LIKE '%关键词%'。\n"
            "3. 只能引用上述表与列；禁止写操作与附件函数。\n"
            "4. 结果建议 LIMIT 100。\n"
            "5. 不要输出英文 reasoning / thinking。"
        )
        result = chat(
            role="big",
            task_type="text2sql",
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": f"问题：{q}\n只输出 SQL："},
            ],
            temperature=0.0,
            max_tokens=256,
        )
        base = AskEngineResult(
            ok=False,
            source="llm_text2sql",
            model=result.model,
            model_request_attempted=result.model_request_attempted,
            model_invoked=result.model_invoked,
            output_available=result.output_available,
            model_state=result.model_state,
            fallback_reason=result.fallback_reason,
            latency_ms=result.latency_ms or 0,
        )
        if not result.ok or not result.output_available:
            base.engine_state = "engine_failed"
            base.error = result.error or "model unavailable"
            return base

        sql = extract_sql(result.text)
        guard = validate_readonly_sql(sql)
        if not guard.ok:
            repair = chat(
                role="big",
                task_type="text2sql_repair",
                messages=[
                    {"role": "system", "content": "只输出一条 DuckDB SELECT/WITH，不要任何其他文字。"},
                    {"role": "user", "content": f"问题：{q}\n表：\n{schema}\nSQL："},
                ],
                temperature=0.0,
                max_tokens=128,
            )
            if repair.ok and repair.output_available:
                sql2 = extract_sql(repair.text)
                guard2 = validate_readonly_sql(sql2)
                if guard2.ok:
                    return AskEngineResult(
                        ok=True,
                        sql=guard2.sql,
                        source="llm_text2sql",
                        engine_state="sql_generated",
                        model=repair.model,
                        model_request_attempted=repair.model_request_attempted,
                        model_invoked=repair.model_invoked,
                        output_available=repair.output_available,
                        model_state=repair.model_state,
                        latency_ms=(base.latency_ms or 0) + (repair.latency_ms or 0),
                    )
            base.engine_state = "guard_failed"
            base.error = _guard_error_zh(guard)
            base.code = guard.code
            base.sql = sql
            return base

        return AskEngineResult(
            ok=True,
            sql=guard.sql,
            source="llm_text2sql",
            engine_state="sql_generated",
            model=base.model,
            model_request_attempted=base.model_request_attempted,
            model_invoked=base.model_invoked,
            output_available=True,
            model_state=base.model_state,
            latency_ms=base.latency_ms,
        )
