# -*- coding: utf-8 -*-
"""Ask engine A/B compare cases (docs/19 Step5)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import config

# 20 条真实物资问数：含指标模板类与复杂 NL2SQL 类。
ASK_COMPARE_CASES: list[dict[str, Any]] = [
    {
        "id": "q01",
        "question": "库存表有多少行",
        "kind": "metric_or_simple",
        "must_contain": ["fact_inventory", "count"],
    },
    {
        "id": "q02",
        "question": "库存总量是多少",
        "kind": "metric",
        "must_contain": ["fact_inventory", "stock_qty"],
    },
    {
        "id": "q03",
        "question": "按库位统计库存记录数，取前10",
        "kind": "complex",
        "must_contain": ["fact_inventory", "location", "group"],
    },
    {
        "id": "q04",
        "question": "查看库存数量最高的10个物资",
        "kind": "complex",
        "must_contain": ["fact_inventory", "stock_qty", "limit"],
    },
    {
        "id": "q05",
        "question": "查看超定额物资",
        "kind": "complex",
        "must_contain": ["fact_inventory", "quota"],
    },
    {
        "id": "q06",
        "question": "查看缺少库位的库存记录",
        "kind": "complex",
        "must_contain": ["fact_inventory", "location"],
    },
    {
        "id": "q07",
        "question": "入库合计是多少",
        "kind": "metric",
        "must_contain": ["fact_stock_flow", "in"],
    },
    {
        "id": "q08",
        "question": "出库合计是多少",
        "kind": "metric",
        "must_contain": ["fact_stock_flow", "out"],
    },
    {
        "id": "q09",
        "question": "按物资类别统计库存记录数",
        "kind": "complex",
        "must_contain": ["fact_inventory", "category", "group"],
    },
    {
        "id": "q10",
        "question": "查看资产状态分布",
        "kind": "complex",
        "must_contain": ["fact_asset", "status"],
    },
    {
        "id": "q11",
        "question": "查看需求金额最高的10条",
        "kind": "complex",
        "must_contain": ["fact_demand", "total_price", "limit"],
    },
    {
        "id": "q12",
        "question": "资产台数有多少",
        "kind": "metric",
        "must_contain": ["fact_asset", "count"],
    },
    {
        "id": "q13",
        "question": "需求总量是多少",
        "kind": "metric",
        "must_contain": ["fact_demand"],
    },
    {
        "id": "q14",
        "question": "零库存物资有多少",
        "kind": "metric",
        "must_contain": ["fact_inventory"],
    },
    {
        "id": "q15",
        "question": "缺少库位的库存有多少",
        "kind": "metric",
        "must_contain": ["fact_inventory", "location"],
    },
    {
        "id": "q16",
        "question": "按类别统计库存量",
        "kind": "complex",
        "must_contain": ["fact_inventory", "category"],
    },
    {
        "id": "q17",
        "question": "呆滞料有多少行",
        "kind": "metric",
        "must_contain": ["fact_inventory"],
    },
    {
        "id": "q18",
        "question": "超定额物资有多少",
        "kind": "metric",
        "must_contain": ["fact_inventory", "quota"],
    },
    {
        "id": "q19",
        "question": "按库位统计库存数量，取前5",
        "kind": "complex",
        "must_contain": ["fact_inventory", "location"],
    },
    {
        "id": "q20",
        "question": "缺少保管人的资产有多少",
        "kind": "metric",
        "must_contain": ["fact_asset"],
    },
]


def score_sql_must_contain(sql: str | None, must_contain: list[str]) -> dict[str, Any]:
    text = (sql or "").lower()
    hits = [m for m in must_contain if m.lower() in text]
    missing = [m for m in must_contain if m.lower() not in text]
    return {
        "contain_ok": len(missing) == 0 and bool(must_contain),
        "hits": hits,
        "missing": missing,
    }


def summarize_engine_runs(details: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(details)
    ok = sum(1 for d in details if d.get("ok"))
    exec_ok = sum(1 for d in details if d.get("exec_ok"))
    contain_ok = sum(1 for d in details if d.get("contain_ok"))
    metric_hits = sum(1 for d in details if d.get("source") == "metric_template")
    fallback = sum(1 for d in details if d.get("engine_fallback"))
    latencies = [int(d["latency_ms"]) for d in details if d.get("latency_ms") is not None]
    return {
        "n": n,
        "ok": ok,
        "ok_rate": round(ok / n, 4) if n else 0.0,
        "exec_ok": exec_ok,
        "exec_rate": round(exec_ok / n, 4) if n else 0.0,
        "contain_ok": contain_ok,
        "contain_rate": round(contain_ok / n, 4) if n else 0.0,
        "metric_template_hits": metric_hits,
        "engine_fallback_count": fallback,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
    }


def _pick_winner(summary: dict[str, dict]) -> str:
    leg = summary.get("legacy") or {}
    van = summary.get("vanna") or {}
    for k in ("exec_rate", "contain_rate", "ok_rate"):
        lv, vv = float(leg.get(k) or 0), float(van.get(k) or 0)
        if vv > lv:
            return "vanna"
        if lv > vv:
            return "legacy"
    return "tie"


def offline_stub(case: dict, engine: str) -> dict:
    """Deterministic offline row for CI when LLM is unavailable."""
    q = case["question"]
    must = case.get("must_contain") or []
    if case.get("kind") in ("metric", "metric_or_simple") and engine in ("legacy", "vanna"):
        sql = f"SELECT COUNT(*) AS v FROM fact_inventory -- offline:{q}"
        if "fact_asset" in must:
            sql = "SELECT COUNT(*) AS v FROM fact_asset"
        elif "fact_demand" in must:
            sql = "SELECT SUM(quantity) AS v FROM fact_demand"
        elif "fact_stock_flow" in must and "in" in must:
            sql = "SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='IN'"
        elif "fact_stock_flow" in must and "out" in must:
            sql = "SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='OUT'"
        elif "quota" in must:
            sql = (
                "SELECT COUNT(*) AS v FROM fact_inventory "
                "WHERE quota_qty>0 AND stock_qty>quota_qty"
            )
        elif "location" in must:
            sql = (
                "SELECT COUNT(*) AS v FROM fact_inventory "
                "WHERE location IS NULL OR TRIM(location)=''"
            )
        contain = score_sql_must_contain(sql, must)
        return {
            "ok": True,
            "exec_ok": True,
            "source": "metric_template",
            "engine_state": "metric_template_hit",
            "engine_fallback": False,
            "model_state": "metric_template_hit",
            "degraded": False,
            "error": None,
            "sql": sql,
            "rows": 1,
            "latency_ms": 0,
            "wall_ms": 0,
            "guard_ok": True,
            "contain_ok": contain["contain_ok"],
            "contain_hits": contain["hits"],
            "contain_missing": contain["missing"],
            "metric_id": "OFFLINE",
            "offline": True,
        }
    return {
        "ok": False,
        "exec_ok": False,
        "source": "vanna" if engine == "vanna" else "llm_text2sql",
        "engine_state": "engine_failed",
        "engine_fallback": engine == "vanna",
        "model_state": "local_model_unavailable",
        "degraded": True,
        "error": "offline mode: LLM not invoked",
        "sql": None,
        "rows": None,
        "latency_ms": 0,
        "wall_ms": 0,
        "guard_ok": False,
        "contain_ok": False,
        "contain_hits": [],
        "contain_missing": list(must),
        "metric_id": None,
        "offline": True,
    }


def _run_one(question: str, must_contain: list[str]) -> dict:
    from app.services.sql_guard import validate_readonly_sql
    from app.services.text2sql import ask

    t0 = time.time()
    res = ask(question)
    wall_ms = int((time.time() - t0) * 1000)
    sql = res.get("sql")
    contain = score_sql_must_contain(sql, must_contain)
    guard = validate_readonly_sql(sql or "") if sql else None
    exec_ok = bool(res.get("ok")) and not res.get("degraded")
    if res.get("ok") and res.get("source") == "metric_template":
        exec_ok = True
    return {
        "ok": bool(res.get("ok")),
        "exec_ok": exec_ok,
        "source": res.get("source"),
        "engine_state": res.get("engine_state"),
        "engine_fallback": bool(res.get("engine_fallback")),
        "model_state": res.get("model_state"),
        "degraded": bool(res.get("degraded")),
        "error": res.get("error"),
        "sql": sql,
        "rows": res.get("rows"),
        "latency_ms": res.get("latency_ms") if res.get("latency_ms") is not None else wall_ms,
        "wall_ms": wall_ms,
        "guard_ok": bool(guard.ok) if guard else False,
        "contain_ok": contain["contain_ok"],
        "contain_hits": contain["hits"],
        "contain_missing": contain["missing"],
        "metric_id": res.get("metric_id"),
    }


def _ensure_runtime() -> None:
    from app.repositories import init_meta, writer_conn
    from app.repositories.schema import ensure_biz_schema
    from app.services.fewshot import ensure_sql_fewshot_seed
    from app.services.metrics import ensure_metrics_seed
    from app.services.query.vanna_train import train_vanna_ask

    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()
    ensure_metrics_seed()
    ensure_sql_fewshot_seed()
    try:
        train_vanna_ask(replace=False)
    except Exception:
        pass


def run_compare(*, offline: bool = False, out_path: Path | None = None) -> dict:
    """Run legacy vs vanna on ASK_COMPARE_CASES; write ask_engine_compare.json."""
    _ensure_runtime()
    out_path = out_path or (config.EVAL / "results" / "ask_engine_compare.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    engines = ("legacy", "vanna")
    by_engine: dict[str, list[dict]] = {e: [] for e in engines}
    cases_out: list[dict] = []

    for case in ASK_COMPARE_CASES:
        row = {
            "id": case["id"],
            "question": case["question"],
            "kind": case["kind"],
            "engines": {},
        }
        for engine in engines:
            if offline:
                detail = offline_stub(case, engine)
            else:
                prev = config.ASK_ENGINE
                try:
                    config.ASK_ENGINE = engine
                    detail = _run_one(case["question"], list(case.get("must_contain") or []))
                finally:
                    config.ASK_ENGINE = prev
            by_engine[engine].append(detail)
            row["engines"][engine] = detail
        cases_out.append(row)

    summary = {e: summarize_engine_runs(by_engine[e]) for e in engines}
    payload = {
        "ok": True,
        "compared_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "offline": offline,
        "n_cases": len(ASK_COMPARE_CASES),
        "summary": summary,
        "winner": _pick_winner(summary),
        "cases": cases_out,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["path"] = str(out_path)
    return payload
