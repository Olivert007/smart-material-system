# -*- coding: utf-8 -*-
"""Metric dictionary + FLOW_* draft seeds (docs/08 + 12 §8 / A9).

FLOW_* stay draft until 08/12 gate checklist passes (activation = Phase D4).
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.repositories import biz_conn, meta_conn, meta_tx
from app.services.flow_gov import parse_stats, reconcile
from app.services.flow_lineage import audit_stock_flow

# definition_sql must be a single SELECT returning column `v` (or first col).
FLOW_DRAFT_METRICS: list[dict[str, Any]] = [
    {
        "metric_id": "FLOW_QTY_TOTAL",
        "metric_name": "流水入库合计（质量门）",
        # U-4：移除「入库总量/出入库总量」等易与业务指标 FLOW_IN_QTY_TOTAL 混用的别名
        "aliases": json.dumps(["流水入库合计"], ensure_ascii=False),
        "unit": "件",
        "definition": "仅入库流水 quantity 合计（质量门口径，与业务指标入库流水合计同 SQL）；须过 12/08 质量门后才可 active",
        "definition_sql": (
            "SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='IN'"
        ),
        "source_tables": "fact_stock_flow",
        "engine": "biz",
        "status": "draft",
        "metric_group": "quality",
    },
    {
        "metric_id": "FLOW_PARSE_L1_RATIO",
        "metric_name": "流水解析 L1 占比",
        "aliases": json.dumps(["L1占比", "流水L1比例"], ensure_ascii=False),
        "unit": "ratio",
        "definition": "L1 行数 / (L1+L2 已发布流水行)；分母为 0 时返回 NULL",
        "definition_sql": (
            "SELECT CASE WHEN COUNT(*) FILTER (WHERE parse_level IN ('L1','L2')) = 0 "
            "THEN NULL ELSE CAST(COUNT(*) FILTER (WHERE parse_level='L1') AS DOUBLE) "
            "/ COUNT(*) FILTER (WHERE parse_level IN ('L1','L2')) END AS v "
            "FROM fact_stock_flow"
        ),
        "source_tables": "fact_stock_flow",
        "engine": "biz",
        "status": "draft",
        "metric_group": "quality",
    },
    {
        "metric_id": "FLOW_RECONCILE_GAP_CNT",
        "metric_name": "勾稽差异行数",
        "aliases": json.dumps(["勾稽差异数", "流水勾稽差异"], ensure_ascii=False),
        "unit": "行",
        "definition": "flow_reconcile_gap 行数；口径 ΣIN−ΣOUT ≟ stock−COALESCE(opening,0)（FL6 允许非零）",
        "definition_sql": "SELECT COUNT(*) AS v FROM flow_reconcile_gap",
        "source_tables": "flow_reconcile_gap",
        "engine": "meta",
        "status": "draft",
        "metric_group": "quality",
    },
]

# Business metrics (docs/08 §3) — seeded active for template-first ask (non-FLOW).
BUSINESS_METRICS: list[dict[str, Any]] = [
    {
        "metric_id": "INV_QTY_TOTAL",
        "metric_name": "库存总数量",
        "aliases": json.dumps(
            ["库存总量", "库存合计", "现有库存合计", "库存总数量是多少"],
            ensure_ascii=False,
        ),
        "unit": "件",
        "definition": "现有库存 stock_qty 合计（含临时库字段若有）",
        "definition_sql": "SELECT SUM(stock_qty) AS v FROM fact_inventory",
        "source_tables": "fact_inventory",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
    },
    {
        "metric_id": "INV_RECORD_CNT",
        "metric_name": "库存记录行数",
        "aliases": json.dumps(
            ["库存表有多少行", "库存记录数", "库存行数", "库存记录条数"],
            ensure_ascii=False,
        ),
        "unit": "行",
        "definition": "库存台账记录行数（COUNT(*)）",
        "definition_sql": "SELECT COUNT(*) AS v FROM fact_inventory",
        "source_tables": "fact_inventory",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
    },
    {
        "metric_id": "INV_VALUE_TOTAL",
        "metric_name": "库存总金额",
        "aliases": json.dumps(
            ["库存金额合计", "库存总额", "库存总金额是多少", "存货金额"],
            ensure_ascii=False,
        ),
        "unit": "元",
        "definition": "stock_value 合计；排除空值（schema 无 is_temp_warehouse 时不做临时库过滤）",
        "definition_sql": (
            "SELECT SUM(stock_value) AS v FROM fact_inventory WHERE stock_value IS NOT NULL"
        ),
        "source_tables": "fact_inventory",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
        "data_check_sql": "SELECT COUNT(*) AS n FROM fact_inventory WHERE stock_value IS NOT NULL",
    },
    {
        "metric_id": "DEMAND_QTY_TOTAL",
        "metric_name": "需求总量",
        "aliases": json.dumps(
            ["需求合计", "需求总数", "需求总量是多少", "需求数量合计"],
            ensure_ascii=False,
        ),
        "unit": "件",
        "definition": "全部期次需求 quantity 合计",
        "definition_sql": "SELECT SUM(quantity) AS v FROM fact_demand",
        "source_tables": "fact_demand",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
    },
    {
        "metric_id": "ASSET_COUNT_TOTAL",
        "metric_name": "资产总数",
        "aliases": json.dumps(
            ["资产合计", "资产台数", "资产总数是多少", "有多少资产"],
            ensure_ascii=False,
        ),
        "unit": "台",
        "definition": "资产行数；排除状态含「待报废」",
        "definition_sql": (
            "SELECT COUNT(*) AS v FROM fact_asset "
            "WHERE COALESCE(status, '') NOT LIKE '%待报废%'"
        ),
        "source_tables": "fact_asset",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
    },
    {
        "metric_id": "INV_OVER_QUOTA_CNT",
        "metric_name": "超定额物资数",
        "aliases": json.dumps(
            ["超定额", "超定额物资", "超定额有多少", "超过定额的物资数"],
            ensure_ascii=False,
        ),
        "unit": "种",
        "definition": "stock_qty > quota_qty 且 quota_qty 非空的库存行数",
        "definition_sql": (
            "SELECT COUNT(*) AS v FROM fact_inventory "
            "WHERE quota_qty IS NOT NULL AND stock_qty IS NOT NULL AND stock_qty > quota_qty"
        ),
        "source_tables": "fact_inventory",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
    },
    {
        "metric_id": "INV_QUOTA_FILL_RATIO",
        "metric_name": "定额利用率",
        "aliases": json.dumps(
            ["定额比", "库存定额比", "定额利用率", "库存占定额比例"],
            ensure_ascii=False,
        ),
        "unit": "ratio",
        "definition": "Σstock_qty / Σquota_qty（仅 quota_qty>0）；无定额时 NULL",
        "definition_sql": (
            "SELECT CASE WHEN SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) = 0 "
            "THEN NULL ELSE CAST(SUM(CASE WHEN quota_qty > 0 THEN stock_qty ELSE 0 END) AS DOUBLE) "
            "/ SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) END AS v "
            "FROM fact_inventory"
        ),
        "source_tables": "fact_inventory",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
    },
    {
        "metric_id": "INV_BELOW_MIN_CNT",
        "metric_name": "低于最低库存物资数",
        "aliases": json.dumps(
            ["最低库存预警", "低于最低库存", "库存不足", "缺货预警"],
            ensure_ascii=False,
        ),
        "unit": "种",
        "definition": "min_qty 非空且 stock_qty < min_qty 的库存行数",
        "definition_sql": (
            "SELECT COUNT(*) AS v FROM fact_inventory "
            "WHERE min_qty IS NOT NULL AND stock_qty IS NOT NULL AND stock_qty < min_qty"
        ),
        "source_tables": "fact_inventory",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
        "data_check_sql": "SELECT COUNT(*) AS n FROM fact_inventory WHERE min_qty IS NOT NULL",
    },
    {
        "metric_id": "INV_EMERGENCY_QUOTA_FILL_RATIO",
        "metric_name": "应急备汛定额利用率",
        "aliases": json.dumps(
            ["应急备汛定额比", "应急物资定额利用率", "备汛定额满足率"],
            ensure_ascii=False,
        ),
        "unit": "ratio",
        "definition": "应急备汛物资 sheet：Σstock_qty/Σquota_qty（仅 quota_qty>0）；无定额时 NULL",
        "definition_sql": (
            "SELECT CASE WHEN SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) = 0 "
            "THEN NULL ELSE CAST(SUM(CASE WHEN quota_qty > 0 THEN stock_qty ELSE 0 END) AS DOUBLE) "
            "/ SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) END AS v "
            "FROM fact_inventory WHERE source_sheet='应急备汛物资'"
        ),
        "source_tables": "fact_inventory",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
        "data_check_sql": (
            "SELECT COUNT(*) AS n FROM fact_inventory "
            "WHERE source_sheet='应急备汛物资' AND quota_qty IS NOT NULL"
        ),
    },
    {
        "metric_id": "INV_STALE_CNT",
        "metric_name": "呆滞料行数",
        "aliases": json.dumps(
            ["呆滞料", "呆滞库存", "超龄库存", "呆滞料有多少"],
            ensure_ascii=False,
        ),
        "unit": "行",
        "definition": "age_days >= 365 的库存行（字段缺失则 0）",
        "definition_sql": (
            "SELECT COUNT(*) AS v FROM fact_inventory "
            "WHERE age_days IS NOT NULL AND age_days >= 365"
        ),
        "source_tables": "fact_inventory",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
        "data_check_sql": "SELECT COUNT(*) AS n FROM fact_inventory WHERE age_days IS NOT NULL",
    },
    {
        "metric_id": "FLOW_IN_QTY_TOTAL",
        "metric_name": "入库流水合计",
        "aliases": json.dumps(
            ["入库合计", "入库流水总量", "本期入库量"],
            ensure_ascii=False,
        ),
        "unit": "件",
        "definition": "fact_stock_flow 入库 quantity 合计（业务指标，非 FLOW_* 质量门）",
        "definition_sql": (
            "SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='IN'"
        ),
        "source_tables": "fact_stock_flow",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
    },
    {
        "metric_id": "FLOW_OUT_QTY_TOTAL",
        "metric_name": "出库流水合计",
        "aliases": json.dumps(
            ["出库合计", "出库流水总量", "本期出库量"],
            ensure_ascii=False,
        ),
        "unit": "件",
        "definition": "fact_stock_flow 出库 quantity 合计",
        "definition_sql": (
            "SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='OUT'"
        ),
        "source_tables": "fact_stock_flow",
        "engine": "biz",
        "status": "active",
        "metric_group": "business",
    },
    {
        "metric_id": "INTAKE_BLOCK_RATE",
        "metric_name": "接入阻断率",
        "aliases": json.dumps(["阻断率", "清洗阻断比例"], ensure_ascii=False),
        "unit": "ratio",
        "definition": "最新 staging blocked/(clean+blocked)；无 staging 时为 0",
        "definition_sql": (
            "SELECT CASE WHEN (COALESCE(clean_rows,0)+COALESCE(blocked_rows,0))=0 THEN 0.0 "
            "ELSE CAST(COALESCE(blocked_rows,0) AS REAL)"
            "/(COALESCE(clean_rows,0)+COALESCE(blocked_rows,0)) END AS v "
            "FROM staging_record ORDER BY updated_at DESC LIMIT 1"
        ),
        "source_tables": "staging_record",
        "engine": "meta",
        "status": "active",
        "metric_group": "ops",
    },
    {
        "metric_id": "INTAKE_CLEAN_RATE",
        "metric_name": "接入清洁率",
        "aliases": json.dumps(["清洁率"], ensure_ascii=False),
        "unit": "ratio",
        "definition": "最新 staging clean/(clean+blocked)",
        "definition_sql": (
            "SELECT CASE WHEN (COALESCE(clean_rows,0)+COALESCE(blocked_rows,0))=0 THEN 1.0 "
            "ELSE CAST(COALESCE(clean_rows,0) AS REAL)"
            "/(COALESCE(clean_rows,0)+COALESCE(blocked_rows,0)) END AS v "
            "FROM staging_record ORDER BY updated_at DESC LIMIT 1"
        ),
        "source_tables": "staging_record",
        "engine": "meta",
        "status": "active",
        "metric_group": "ops",
    },
]

_FLOW_IDS = {m["metric_id"] for m in FLOW_DRAFT_METRICS}
_BIZ_IDS = {m["metric_id"] for m in BUSINESS_METRICS}
_SELECT_OK = re.compile(r"^\s*SELECT\b", re.I)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|COPY|CREATE|REPLACE|TRUNCATE|PRAGMA)\b",
    re.I,
)


def _seed_metric_rows(metrics: list[dict[str, Any]], *, actor: str) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    with meta_tx() as con:
        for m in metrics:
            row = con.execute(
                "SELECT metric_id, status FROM metric_dict WHERE metric_id=?",
                [m["metric_id"]],
            ).fetchone()
            if row:
                skipped += 1
                continue
            con.execute(
                """
                INSERT INTO metric_dict (
                    metric_id, metric_name, aliases, unit, definition, definition_sql,
                    source_tables, status, version, engine, confirmed_by,
                    metric_group, data_check_sql
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                [
                    m["metric_id"],
                    m["metric_name"],
                    m.get("aliases") or "[]",
                    m.get("unit") or "",
                    m.get("definition") or "",
                    m["definition_sql"],
                    m.get("source_tables") or "",
                    m.get("status") or "draft",
                    m.get("engine") or "biz",
                    actor,
                    m.get("metric_group") or "business",
                    m.get("data_check_sql"),
                ],
            )
            inserted += 1
    return inserted, skipped


def _sync_seed_metadata() -> int:
    """幂等数据迁移（U-1/U-3/U-4）：回填 metric_group / data_check_sql；收紧 FLOW_QTY_TOTAL 展示名与别名。

    - 分组与数据探针为种子元数据，直接按代码同步；
    - FLOW_QTY_TOTAL 展示名/别名仅当仍为旧种子值时迁移，避免覆盖人工编辑。
    """
    changed = 0
    _old_flow_qty = {"metric_name": "出入库总量（入库）"}
    with meta_tx() as con:
        for m in FLOW_DRAFT_METRICS + BUSINESS_METRICS:
            row = con.execute(
                "SELECT metric_group, data_check_sql FROM metric_dict WHERE metric_id=?",
                [m["metric_id"]],
            ).fetchone()
            if not row:
                continue
            new_group = m.get("metric_group") or "business"
            new_dcs = m.get("data_check_sql")
            if row["metric_group"] != new_group or row["data_check_sql"] != new_dcs:
                con.execute(
                    "UPDATE metric_dict SET metric_group=?, data_check_sql=?, updated_at=datetime('now') WHERE metric_id=?",
                    [new_group, new_dcs, m["metric_id"]],
                )
                changed += 1
        row = con.execute(
            "SELECT metric_name FROM metric_dict WHERE metric_id='FLOW_QTY_TOTAL'"
        ).fetchone()
        if row and row["metric_name"] == _old_flow_qty["metric_name"]:
            con.execute(
                "UPDATE metric_dict SET metric_name=?, aliases=?, updated_at=datetime('now') WHERE metric_id='FLOW_QTY_TOTAL'",
                [FLOW_DRAFT_METRICS[0]["metric_name"], FLOW_DRAFT_METRICS[0]["aliases"]],
            )
            changed += 1
    return changed


def ensure_flow_metrics_draft(*, actor: str = "system:seed") -> dict:
    """Idempotent seed: insert missing FLOW_* as draft. Never demote active."""
    inserted, skipped = _seed_metric_rows(FLOW_DRAFT_METRICS, actor=actor)
    return {"ok": True, "inserted": inserted, "skipped": skipped, "draft_ids": sorted(_FLOW_IDS)}


def ensure_business_metrics(*, actor: str = "system:seed") -> dict:
    """Idempotent seed INV_/DEMAND_/ASSET_* (active) for template-first ask."""
    inserted, skipped = _seed_metric_rows(BUSINESS_METRICS, actor=actor)
    return {"ok": True, "inserted": inserted, "skipped": skipped, "ids": sorted(_BIZ_IDS)}


def ensure_metrics_seed(*, actor: str = "system:seed") -> dict:
    a = ensure_flow_metrics_draft(actor=actor)
    b = ensure_business_metrics(actor=actor)
    synced = _sync_seed_metadata()
    return {"ok": True, "flow": a, "business": b, "synced": synced}

def list_metrics(*, status: str | None = None) -> dict:
    ensure_metrics_seed()
    con = meta_conn()
    try:
        if status:
            rows = con.execute(
                "SELECT * FROM metric_dict WHERE status=? ORDER BY metric_id",
                [status],
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM metric_dict ORDER BY metric_id").fetchall()
    finally:
        con.close()
    return {"total": len(rows), "items": [_row_to_dict(r) for r in rows]}


def get_metric(metric_id: str) -> dict:
    ensure_metrics_seed()
    con = meta_conn()
    try:
        row = con.execute(
            "SELECT * FROM metric_dict WHERE metric_id=?", [metric_id]
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise KeyError(metric_id)
    return _row_to_dict(row)


def _alias_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except json.JSONDecodeError:
            return [raw]
    return []


# docs/08 §5：指标模板只应答单值口径；分组/分布/排名/前N 属明细查询，走 LLM
_GROUP_INTENT_RE = re.compile(
    r"(按[^，。？、\s]{1,10}(?:汇总|统计|分布|排行|排名)|(?:排行|排名|分布|占比|前\d+名?|明细|清单))"
)


def match_metrics(question: str, *, limit: int = 5) -> dict[str, Any]:
    """Rule match question → metric candidates (docs/08 §5 / §8)."""
    ensure_metrics_seed()
    q = (question or "").strip()
    if not q:
        return {"question": q, "candidates": [], "conflict": False, "best": None}

    q_norm = re.sub(r"\s+", "", q.lower())
    if _GROUP_INTENT_RE.search(q_norm):
        return {
            "question": q,
            "candidates": [],
            "conflict": False,
            "best": None,
            "group_intent": True,
        }
    items = list_metrics()["items"]
    scored: list[dict[str, Any]] = []
    for m in items:
        name = str(m.get("metric_name") or "")
        aliases = _alias_list(m.get("aliases"))
        score = 0.0
        hit = None
        name_n = re.sub(r"\s+", "", name.lower())
        if name_n and name_n in q_norm:
            score = 1.0
            hit = name
        else:
            for a in aliases:
                a_n = re.sub(r"\s+", "", str(a).lower())
                if not a_n:
                    continue
                if a_n in q_norm or q_norm in a_n:
                    # longer alias wins
                    s = 0.85 + min(len(a_n), 40) / 200.0
                    if s > score:
                        score = s
                        hit = a
        if score <= 0:
            continue
        # Prefer active slightly
        if m.get("status") == "active":
            score += 0.05
        scored.append(
            {
                "metric_id": m["metric_id"],
                "metric_name": name,
                "status": m.get("status"),
                "score": round(score, 4),
                "matched_alias": hit,
                "definition_sql": m.get("definition_sql"),
                "unit": m.get("unit"),
                "engine": m.get("engine"),
            }
        )
    scored.sort(key=lambda x: (-x["score"], x["metric_id"]))
    top = scored[:limit]
    conflict = False
    best = None
    if len(top) >= 2 and abs(top[0]["score"] - top[1]["score"]) < 0.08:
        conflict = True
    elif top:
        best = top[0]
    return {
        "question": q,
        "candidates": top,
        "conflict": conflict,
        "best": best if not conflict else None,
    }


def check_metric_conflicts() -> dict[str, Any]:
    """Detect overlapping aliases / names across metrics (docs/08 C4)."""
    ensure_metrics_seed()
    items = list_metrics()["items"]
    alias_map: dict[str, list[str]] = {}
    for m in items:
        mid = m["metric_id"]
        names = [str(m.get("metric_name") or "")] + _alias_list(m.get("aliases"))
        for n in names:
            key = re.sub(r"\s+", "", n.strip().lower())
            if not key:
                continue
            alias_map.setdefault(key, []).append(mid)
    conflicts = []
    for alias, mids in sorted(alias_map.items()):
        uniq = sorted(set(mids))
        if len(uniq) >= 2:
            conflicts.append({"alias": alias, "metric_ids": uniq})
    return {
        "ok": len(conflicts) == 0,
        "conflict_count": len(conflicts),
        "conflicts": conflicts[:100],
        "hint": "同义别名跨指标冲突须人工改别名；问答命中冲突返回 METRIC_CONFLICT",
    }


def list_metric_snapshots(metric_id: str, *, limit: int = 20) -> dict:
    limit = max(1, min(int(limit), 100))
    with meta_tx() as con:
        rows = con.execute(
            """
            SELECT snapshot_id, metric_id, value, unit, status, evaluated_at
            FROM metric_snapshot
            WHERE metric_id=?
            ORDER BY evaluated_at DESC
            LIMIT ?
            """,
            [metric_id, limit],
        ).fetchall()
    return {"metric_id": metric_id, "total": len(rows), "items": [dict(r) for r in rows]}


def snapshot_business_metrics(*, actor: str = "system:cron") -> dict:
    """UI-3：对 metric_group=business 的 active 指标统一 evaluate 并写历史快照。

    幂等：单指标失败不影响其余（evaluate_metric 内部已容错 data_check_sql 探针）。
    """
    items = list_metrics(status="active")["items"]
    targets = [m for m in items if (m.get("metric_group") or "business") == "business"]
    ok, failed, skipped = [], [], []
    for m in targets:
        mid = m["metric_id"]
        try:
            out = evaluate_metric(mid, write_snapshot=True)
            (ok if out.get("data_status") != "no_data" else skipped).append(
                {"metric_id": mid, "value": out.get("value"), "data_status": out.get("data_status")}
            )
        except Exception as e:  # noqa: BLE001 — cron 容错
            failed.append({"metric_id": mid, "error": str(e)[:200]})
    return {
        "ok": True,
        "actor": actor,
        "targets": len(targets),
        "snapshotted": len(ok),
        "skipped_no_data": len(skipped),
        "failed": len(failed),
        "items": ok + skipped,
        "errors": failed,
    }


def upsert_metric(
    *,
    metric_id: str,
    metric_name: str,
    definition_sql: str,
    actor: str,
    aliases: list[str] | None = None,
    unit: str = "",
    definition: str = "",
    source_tables: str = "",
    engine: str = "biz",
    status: str = "draft",
) -> dict:
    """Create or version-bump. FLOW_* cannot become active here (08/12 gate)."""
    status = (status or "draft").lower().strip()
    if status not in ("draft", "active", "deprecated"):
        raise ValueError("status must be draft|active|deprecated")
    if not _SELECT_OK.match(definition_sql or "") or _FORBIDDEN.search(definition_sql or ""):
        raise ValueError("definition_sql must be a read-only SELECT")
    if metric_id.startswith("FLOW_") and status == "active":
        gate = flow_activation_gate()
        if not gate["ready"]:
            raise PermissionError(
                f"FLOW_* cannot be active until gate passes: {gate['missing']}"
            )

    with meta_tx() as con:
        existing = con.execute(
            "SELECT * FROM metric_dict WHERE metric_id=?", [metric_id]
        ).fetchone()
        if not existing:
            con.execute(
                """
                INSERT INTO metric_dict (
                    metric_id, metric_name, aliases, unit, definition, definition_sql,
                    source_tables, status, version, engine, confirmed_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                [
                    metric_id,
                    metric_name,
                    json.dumps(aliases or [], ensure_ascii=False),
                    unit,
                    definition,
                    definition_sql,
                    source_tables,
                    status,
                    engine,
                    actor,
                ],
            )
            ver = 1
        else:
            ver = int(existing["version"]) + 1
            con.execute(
                """
                UPDATE metric_dict SET
                    metric_name=?, aliases=?, unit=?, definition=?, definition_sql=?,
                    source_tables=?, status=?, version=?, engine=?, confirmed_by=?,
                    updated_at=datetime('now')
                WHERE metric_id=?
                """,
                [
                    metric_name,
                    json.dumps(aliases or [], ensure_ascii=False),
                    unit,
                    definition,
                    definition_sql,
                    source_tables,
                    status,
                    ver,
                    engine,
                    actor,
                    metric_id,
                ],
            )
    return get_metric(metric_id) | {"version": ver, "actor": actor}


def evaluate_metric(metric_id: str, *, write_snapshot: bool = True) -> dict:
    m = get_metric(metric_id)
    sql = m["definition_sql"]
    engine = (m.get("engine") or "biz").lower()
    if not _SELECT_OK.match(sql) or _FORBIDDEN.search(sql):
        raise ValueError("unsafe definition_sql")
    value = None
    if engine == "meta":
        con = meta_conn()
        try:
            row = con.execute(sql).fetchone()
            value = None if row is None else row[0]
        finally:
            con.close()
    else:
        con = biz_conn()
        try:
            row = con.execute(sql).fetchone()
            value = None if row is None else row[0]
        finally:
            con.close()
    data_status = "ok" if value is not None else "no_data"
    note_extra = None
    dcs = (m.get("data_check_sql") or "").strip()
    if dcs:
        con2 = meta_conn() if engine == "meta" else biz_conn()
        try:
            n = con2.execute(dcs).fetchone()
            n = 0 if n is None else int(n[0] or 0)
        except Exception:
            n = -1  # 探针失败时保持原有行为
        finally:
            con2.close()
        if n == 0:
            value = None
            data_status = "no_data"
            note_extra = "该字段当前无有效数据"
    if value is not None:
        try:
            value = float(value)
            if value == int(value):
                value = int(value)
        except (TypeError, ValueError):
            pass
    out = {
        "metric_id": metric_id,
        "status": m["status"],
        "version": m["version"],
        "value": value,
        "unit": m.get("unit"),
        "engine": engine,
        "active": m["status"] == "active",
        "data_status": data_status,
        "note": (
            note_extra
            or ("流水质量未达标，指标保持 draft" if metric_id.startswith("FLOW_") and m["status"] != "active" else None)
        ),
    }
    if write_snapshot:
        with meta_tx() as con:
            con.execute(
                """
                INSERT INTO metric_snapshot (metric_id, value, unit, status)
                VALUES (?, ?, ?, ?)
                """,
                [
                    metric_id,
                    float(value) if isinstance(value, (int, float)) else None,
                    m.get("unit"),
                    m.get("status"),
                ],
            )
        out["snapshot_written"] = True
    return out


def flow_activation_gate() -> dict:
    """08/12 §8 checklist — all must pass before FLOW_QTY_TOTAL may go active."""
    from app.services.metric_fixtures import run_metric_fixtures

    stats = parse_stats()
    audit = audit_stock_flow(limit=5000)
    year_qty = sum(
        1
        for s in audit.get("suspicious") or []
        if "year_as_quantity" in (s.get("reasons") or [])
    )
    try:
        # GET surfaces must not rewrite flow_reconcile_gap (P0-1 / C1).
        rec = reconcile(persist=False)
        reconcile_ok = True
        gap_total = int(rec.get("total") or 0)
    except Exception as e:
        reconcile_ok = False
        gap_total = None
        rec_err = str(e)
    else:
        rec_err = None

    fixtures = run_metric_fixtures(metric_ids=["FLOW_QTY_TOTAL", "FLOW_PARSE_L1_RATIO", "FLOW_RECONCILE_GAP_CNT"])

    # Lineage rebuild capability (FL7): clean of year-qty after audit (= rebuild path available + applied)
    lineage_ok = year_qty == 0 and bool(audit.get("ok"))

    checks = {
        "rule_path_has_published_rows": (stats.get("published_total") or 0) > 0,
        "l1_l2_l3_stats_available": isinstance(stats.get("published_by_level"), dict),
        "no_year_as_quantity": lineage_ok,
        "reconcile_runnable": reconcile_ok,
        "fixture_tests_passed": bool(fixtures.get("ok")),
        "lineage_rebuild_clean": lineage_ok,
    }
    missing = [k for k, ok in checks.items() if not ok]
    return {
        "ready": len(missing) == 0,
        "checks": checks,
        "missing": missing,
        "fixtures": fixtures,
        "stats": {
            "published_by_level": stats.get("published_by_level"),
            "published_total": stats.get("published_total"),
            "l1_ratio": stats.get("l1_ratio"),
            "pending": stats.get("pending"),
            "year_as_quantity": year_qty,
            "reconcile_gap_cnt": gap_total,
            "reconcile_error": rec_err,
        },
    }


def activate_flow_metrics(
    *,
    actor: str,
    metric_ids: list[str] | None = None,
) -> dict:
    """Promote FLOW_* to active when 08/12 gate is ready (D4)."""
    ensure_flow_metrics_draft()
    gate = flow_activation_gate()
    if not gate["ready"]:
        raise PermissionError(f"gate not ready: {gate['missing']}")

    targets = metric_ids or ["FLOW_QTY_TOTAL", "FLOW_PARSE_L1_RATIO", "FLOW_RECONCILE_GAP_CNT"]
    activated = []
    with meta_tx() as con:
        for mid in targets:
            if not mid.startswith("FLOW_"):
                continue
            row = con.execute(
                "SELECT metric_id, status, version FROM metric_dict WHERE metric_id=?",
                [mid],
            ).fetchone()
            if not row:
                continue
            if row["status"] == "active":
                activated.append({"metric_id": mid, "version": row["version"], "idempotent": True})
                continue
            ver = int(row["version"]) + 1
            con.execute(
                """
                UPDATE metric_dict
                SET status='active', version=?, confirmed_by=?, updated_at=datetime('now')
                WHERE metric_id=?
                """,
                [ver, actor, mid],
            )
            activated.append({"metric_id": mid, "version": ver, "idempotent": False})
        con.execute(
            """
            INSERT INTO write_audit (action, release_id, actor, detail_json)
            VALUES ('metric_activate_flow', NULL, ?, ?)
            """,
            [
                actor,
                json.dumps({"activated": activated, "gate": gate["checks"]}, ensure_ascii=False),
            ],
        )
    return {"ok": True, "activated": activated, "gate": gate}


def flow_quality_baseline() -> dict:
    """A9/D4: baseline numbers + gate; reports draft/active mix."""
    ensure_flow_metrics_draft()
    stats = parse_stats()
    gate = flow_activation_gate()
    values = {}
    statuses = {}
    for mid in sorted(_FLOW_IDS):
        try:
            m = get_metric(mid)
            statuses[mid] = m.get("status")
            values[mid] = evaluate_metric(mid)
        except Exception as e:
            values[mid] = {"metric_id": mid, "error": str(e)}
    return {
        "ok": True,
        "parse_stats": stats,
        "gate": gate,
        "metric_values": values,
        "metric_status": statuses,
        "flow_metrics_all_draft": all(s == "draft" for s in statuses.values()),
        "flow_active_forbidden_until": gate["missing"],
    }


def _row_to_dict(row: Any) -> dict:
    d = dict(row)
    try:
        d["aliases"] = json.loads(d.get("aliases") or "[]")
    except json.JSONDecodeError:
        d["aliases"] = []
    return d
