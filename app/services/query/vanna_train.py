# -*- coding: utf-8 -*-
"""Build Vanna ask context from trusted local sources (docs/19 Step3)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import config
from app.repositories import meta_conn
from app.services.fewshot import ensure_sql_fewshot_seed
from app.services.metrics import ensure_metrics_seed, list_metrics
from app.services.query.text2sql import SCHEMA_ZH, schema_summary

# 物资领域手写样例（与执行方案 §8 对齐）
DOMAIN_QUESTION_SQL: list[tuple[str, str]] = [
    (
        "库存表有多少行",
        "SELECT COUNT(*) AS row_count FROM fact_inventory",
    ),
    (
        "按库位统计库存记录数，取前10",
        "SELECT location, COUNT(*) AS cnt FROM fact_inventory "
        "GROUP BY location ORDER BY cnt DESC LIMIT 10",
    ),
    (
        "查看库存数量最高的10个物资",
        "SELECT i.material_id, m.material_name, i.stock_qty, i.location "
        "FROM fact_inventory i "
        "LEFT JOIN dim_material m ON i.material_id = m.material_id "
        "ORDER BY i.stock_qty DESC NULLS LAST LIMIT 10",
    ),
    (
        "查看超定额物资",
        "SELECT * FROM fact_inventory "
        "WHERE quota_qty > 0 AND stock_qty > quota_qty LIMIT 100",
    ),
    (
        "查看缺少库位的库存记录",
        "SELECT * FROM fact_inventory "
        "WHERE location IS NULL OR TRIM(location) = '' LIMIT 100",
    ),
    (
        "入库合计是多少",
        "SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type = 'IN'",
    ),
    (
        "出库合计是多少",
        "SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type = 'OUT'",
    ),
    (
        "按物资类别统计库存记录数",
        "SELECT category, COUNT(*) AS cnt FROM fact_inventory "
        "GROUP BY category ORDER BY cnt DESC LIMIT 100",
    ),
    (
        "查看资产状态分布",
        "SELECT status, COUNT(*) AS cnt FROM fact_asset "
        "GROUP BY status ORDER BY cnt DESC",
    ),
    (
        "查看需求金额最高的10条",
        "SELECT * FROM fact_demand ORDER BY total_price DESC NULLS LAST LIMIT 10",
    ),
]


def _norm_key(question: str, sql: str) -> tuple[str, str]:
    q = re.sub(r"\s+", "", (question or "").strip().lower())
    s = re.sub(r"\s+", " ", (sql or "").strip().lower().rstrip(";"))
    return q, s


def _alias_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return []


def schema_zh_documentation() -> str:
    lines = ["SCHEMA_ZH 中文字段说明："]
    for table, cols in SCHEMA_ZH.items():
        lines.append(f"表 {table}:")
        for col, zh in cols.items():
            lines.append(f"  - {col}: {zh}")
    return "\n".join(lines)


def ddl_from_schema_summary(summary: str) -> list[str]:
    """Split schema summary into per-table DDL-ish chunks for Vanna retrieval."""
    blocks: list[str] = []
    cur: list[str] = []
    for line in (summary or "").splitlines():
        if line.startswith("表 ") and cur:
            blocks.append("\n".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return [b for b in blocks if b.strip()]


def collect_question_sql_pairs() -> list[dict[str, str]]:
    ensure_metrics_seed()
    ensure_sql_fewshot_seed()
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []

    def add(question: str, sql: str, source: str) -> None:
        q = (question or "").strip()
        s = (sql or "").strip().rstrip(";")
        if not q or not s:
            return
        key = _norm_key(q, s)
        if key in seen:
            return
        seen.add(key)
        out.append({"question": q, "sql": s, "source": source})

    for question, sql in DOMAIN_QUESTION_SQL:
        add(question, sql, "domain_sample")

    for row in list_metrics(status="active")["items"]:
        sql = str(row.get("definition_sql") or "").strip()
        if not sql:
            continue
        name = str(row.get("metric_name") or "").strip()
        mid = str(row.get("metric_id") or "")
        if name:
            add(name, sql, f"metric:{mid}")
        for alias in _alias_list(row.get("aliases")):
            add(alias, sql, f"metric_alias:{mid}")

    con = meta_conn()
    try:
        rows = con.execute(
            "SELECT question, sql_gold, source FROM sql_fewshot ORDER BY updated_at DESC"
        ).fetchall()
    except Exception:
        rows = []
    finally:
        con.close()
    for r in rows:
        src = r["source"] if "source" in r.keys() else "db"
        add(r["question"], r["sql_gold"], f"fewshot:{src or 'db'}")

    return out


def collect_training_payload() -> dict[str, Any]:
    summary = schema_summary()
    doc_parts = [
        "DuckDB 物资管理库 schema 摘要（只读问数）：",
        summary,
        "",
        schema_zh_documentation(),
        "",
        "约定：中文条件用 LIKE；结果建议 LIMIT 100；仅 SELECT/WITH。",
    ]
    documentation = [("\n".join(doc_parts)).strip()]
    ddl = ddl_from_schema_summary(summary)
    question_sql = collect_question_sql_pairs()
    return {
        "documentation": documentation,
        "ddl": ddl,
        "question_sql": question_sql,
    }


def train_vanna_ask(*, replace: bool = True) -> dict[str, Any]:
    """Initialize / refresh Vanna store under VANNA_PERSIST_DIR."""
    from app.services.query.vanna_local import reset_sms_vanna, write_training_store

    payload = collect_training_payload()
    root = Path(config.VANNA_PERSIST_DIR)
    root.mkdir(parents=True, exist_ok=True)
    stats = write_training_store(payload, replace=replace)
    manifest = {
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "persist_dir": str(root),
        "replace": replace,
        **stats,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    reset_sms_vanna()
    return {"ok": True, **manifest}
