# -*- coding: utf-8 -*-
"""Dashboard overview stats (docs/07 §3.1)."""
from __future__ import annotations

from typing import Any

from app.repositories import biz_conn, meta_conn
from app.services import flow_gov as flow_gov_svc
from app.services import metrics as metrics_svc
from app.services.model_client import probe_endpoint
from app import config


_BIZ_TABLES = (
    "dim_material",
    "fact_inventory",
    "fact_asset",
    "fact_demand",
    "fact_stock_flow",
    "fact_quota_adjust",
)


def _table_counts() -> dict[str, int]:
    con = biz_conn()
    out: dict[str, int] = {}
    try:
        for t in _BIZ_TABLES:
            try:
                out[t] = int(con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
            except Exception:
                out[t] = 0
    finally:
        con.close()
    return out


def _recent_files(limit: int = 5) -> list[dict[str, Any]]:
    con = meta_conn()
    try:
        rows = con.execute(
            """
            SELECT file_id, filename, format, rows, sheets, status, created_at
            FROM file_batch
            ORDER BY created_at DESC, file_id DESC
            LIMIT ?
            """,
            [max(1, min(limit, 20))],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def _pending_count() -> int:
    con = meta_conn()
    try:
        return int(
            con.execute(
                "SELECT COUNT(*) AS c FROM flow_pending WHERE status='pending'"
            ).fetchone()["c"]
        )
    finally:
        con.close()


def _scalar(con, sql: str) -> float | int | None:
    try:
        row = con.execute(sql).fetchone()
        if not row:
            return None
        v = row[0]
        if v is None:
            return None
        if isinstance(v, float):
            return float(v)
        return int(v) if float(v) == int(v) else float(v)
    except Exception:
        return None


def business_snapshot(*, top_n: int = 5) -> dict[str, Any]:
    """Read-only business aggregates for home dashboard (analysis surface)."""
    n = max(1, min(int(top_n), 20))
    con = biz_conn()
    try:
        stock_qty = _scalar(con, "SELECT SUM(stock_qty) FROM fact_inventory")
        stock_value = _scalar(
            con, "SELECT SUM(stock_value) FROM fact_inventory WHERE stock_value IS NOT NULL"
        )
        quota_fill = _scalar(
            con,
            """
            SELECT CASE WHEN SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) = 0
            THEN NULL ELSE CAST(SUM(CASE WHEN quota_qty > 0 THEN stock_qty ELSE 0 END) AS DOUBLE)
            / SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) END
            FROM fact_inventory
            """,
        )
        over_quota = _scalar(
            con,
            """
            SELECT COUNT(*) FROM fact_inventory
            WHERE quota_qty IS NOT NULL AND stock_qty IS NOT NULL AND stock_qty > quota_qty
            """,
        )
        stale = _scalar(
            con,
            "SELECT COUNT(*) FROM fact_inventory WHERE age_days IS NOT NULL AND age_days >= 365",
        )
        demand_qty = _scalar(con, "SELECT SUM(quantity) FROM fact_demand")
        asset_cnt = _scalar(
            con,
            "SELECT COUNT(*) FROM fact_asset WHERE COALESCE(status, '') NOT LIKE '%待报废%'",
        )
        flow_in = _scalar(
            con, "SELECT SUM(quantity) FROM fact_stock_flow WHERE flow_type='IN'"
        )
        flow_out = _scalar(
            con, "SELECT SUM(quantity) FROM fact_stock_flow WHERE flow_type='OUT'"
        )

        def _top(sql: str) -> list[dict[str, Any]]:
            try:
                rows = con.execute(sql).fetchall()
                out = []
                for r in rows:
                    out.append(
                        {
                            "name": r[0] if r[0] not in (None, "") else "(空)",
                            "value": float(r[1] or 0),
                        }
                    )
                return out
            except Exception:
                return []

        by_category = _top(
            f"""
            SELECT COALESCE(category, '(空)') AS k, SUM(COALESCE(stock_qty, 0)) AS v
            FROM fact_inventory
            GROUP BY 1
            ORDER BY v DESC
            LIMIT {n}
            """
        )
        by_location = _top(
            f"""
            SELECT COALESCE(location, '(空)') AS k, SUM(COALESCE(stock_qty, 0)) AS v
            FROM fact_inventory
            GROUP BY 1
            ORDER BY v DESC
            LIMIT {n}
            """
        )
        # U-2：库存量跨单位（件/米/对/包）求和无业务含义 → 按单位分组 Top 供对照
        by_unit = _top(
            f"""
            SELECT COALESCE(unit, '(空)') AS k, SUM(COALESCE(stock_qty, 0)) AS v
            FROM fact_inventory
            GROUP BY 1
            ORDER BY v DESC
            LIMIT {n}
            """
        )
        return {
            "stock_qty_total": stock_qty,
            "stock_value_total": stock_value,
            "quota_fill_ratio": quota_fill,
            "over_quota_count": over_quota,
            "stale_count": stale,
            "demand_qty_total": demand_qty,
            "asset_count": asset_cnt,
            "flow_in_qty": flow_in,
            "flow_out_qty": flow_out,
            "top_by_category": by_category,
            "top_by_location": by_location,
            "top_by_unit": by_unit,
        }
    finally:
        con.close()


def _meta_count(sql: str, params: list[Any] | None = None) -> int:
    con = meta_conn()
    try:
        row = con.execute(sql, params or []).fetchone()
        return int(row[0] if row else 0)
    except Exception:
        return 0
    finally:
        con.close()


def _quality_totals() -> dict[str, int]:
    """Sum clean/blocked from latest staging per file; fall back to release_manifest."""
    con = meta_conn()
    try:
        row = con.execute(
            """
            SELECT
              COALESCE(SUM(s.clean_rows), 0) AS clean_rows,
              COALESCE(SUM(s.blocked_rows), 0) AS blocked_rows
            FROM staging_record s
            INNER JOIN (
              SELECT file_id, MAX(updated_at) AS max_updated
              FROM staging_record
              GROUP BY file_id
            ) latest
              ON s.file_id = latest.file_id AND s.updated_at = latest.max_updated
            """
        ).fetchone()
        clean = int(row["clean_rows"] if row else 0)
        blocked = int(row["blocked_rows"] if row else 0)
        if clean or blocked:
            return {"clean_rows": clean, "blocked_rows": blocked}
        # superseded_by may be missing on very old DBs — try/except below
        try:
            row2 = con.execute(
                """
                SELECT
                  COALESCE(SUM(clean_rows), 0) AS clean_rows,
                  COALESCE(SUM(blocked_rows), 0) AS blocked_rows
                FROM release_manifest
                WHERE COALESCE(status, 'released') = 'released'
                  AND (superseded_by IS NULL OR superseded_by = '')
                """
            ).fetchone()
        except Exception:
            row2 = con.execute(
                """
                SELECT
                  COALESCE(SUM(clean_rows), 0) AS clean_rows,
                  COALESCE(SUM(blocked_rows), 0) AS blocked_rows
                FROM release_manifest
                WHERE COALESCE(status, 'released') = 'released'
                """
            ).fetchone()
        return {
            "clean_rows": int(row2["clean_rows"] if row2 else 0),
            "blocked_rows": int(row2["blocked_rows"] if row2 else 0),
        }
    except Exception:
        try:
            row = con.execute(
                """
                SELECT
                  COALESCE(SUM(clean_rows), 0) AS clean_rows,
                  COALESCE(SUM(blocked_rows), 0) AS blocked_rows
                FROM staging_record
                """
            ).fetchone()
            return {
                "clean_rows": int(row["clean_rows"] if row else 0),
                "blocked_rows": int(row["blocked_rows"] if row else 0),
            }
        except Exception:
            return {"clean_rows": 0, "blocked_rows": 0}
    finally:
        con.close()


def _todo_counts(*, flow_pending: int) -> dict[str, int]:
    map_pending = _meta_count(
        "SELECT COUNT(*) FROM map_pending WHERE status='pending'"
    )
    master_pending = _meta_count(
        "SELECT COUNT(*) FROM master_pending WHERE status='pending'"
    )
    material_align = _meta_count(
        "SELECT COUNT(*) FROM material_align WHERE status='proposed'"
    )
    flow_n = int(flow_pending or 0)
    return {
        "map_pending": map_pending,
        "master_pending": master_pending,
        "flow_pending": flow_n,
        "material_align": material_align,
        "ai_suggestion_pending": map_pending + master_pending + material_align + flow_n,
        "total": map_pending + master_pending + flow_n + material_align,
    }


def _next_action(
    *,
    recent_files: list[dict[str, Any]],
    quality: dict[str, int],
    todos: dict[str, int],
    gate_ready: bool | None,
) -> dict[str, str]:
    """Heuristic CTA for workbench first screen (product language)."""
    if not recent_files:
        return {
            "code": "intake",
            "label": "上传物资文件",
            "path": "/intake",
            "reason": "尚未接入文件，请先上传原始数据。",
        }
    if int(todos.get("total") or 0) > 0:
        parts = []
        if todos.get("map_pending"):
            parts.append(f"待确认字段 {todos['map_pending']}")
        if todos.get("master_pending"):
            parts.append(f"待匹配物资 {todos['master_pending']}")
        if todos.get("flow_pending"):
            parts.append(f"流水待确认 {todos['flow_pending']}")
        if todos.get("material_align"):
            parts.append(f"物资对齐 {todos['material_align']}")
        return {
            "code": "ai_review",
            "label": "审核 AI 建议",
            "path": "/govern?tab=map",
            "reason": "；".join(parts) + "。AI 建议须人工确认后才会进入可用数据。",
        }
    if int(quality.get("blocked_rows") or 0) > 0:
        return {
            "code": "govern_blocked",
            "label": "查看阻塞数据",
            "path": "/govern?type=exception",
            "reason": f"当前有 {quality['blocked_rows']} 条阻塞记录，需处理后方可进入可用结果。",
        }
    if gate_ready is False:
        return {
            "code": "gate",
            "label": "继续数据规整",
            "path": "/govern",
            "reason": "数据门禁尚未就绪，规整完成前问数与报表仅供参考。",
        }
    if int(quality.get("clean_rows") or 0) > 0:
        return {
            "code": "data",
            "label": "查看数据成果",
            "path": "/data",
            "reason": "当前有可用候选数据，可浏览明细或导出（不等于正式发布）。",
        }
    return {
        "code": "intake_continue",
        "label": "继续数据接入",
        "path": "/intake",
        "reason": "暂无可用候选数据，请确认接入与规整流程。",
    }


def overview(*, recent_limit: int = 5) -> dict[str, Any]:
    import asyncio

    tables = _table_counts()
    flow = flow_gov_svc.parse_stats()
    gate = metrics_svc.flow_activation_gate()
    recent_files = _recent_files(recent_limit)
    flow_pending = (
        flow.get("pending") if flow.get("pending") is not None else _pending_count()
    )
    quality = _quality_totals()
    todos = _todo_counts(flow_pending=int(flow_pending or 0))
    next_action = _next_action(
        recent_files=recent_files,
        quality=quality,
        todos=todos,
        gate_ready=gate.get("ready"),
    )
    try:
        from app.services.govern import todo_board as todo_board_svc

        estimated_releasable = todo_board_svc.estimated_releasable_rows(
            blocked=int(quality.get("blocked_rows") or 0)
        )
    except Exception:
        estimated_releasable = int(quality.get("blocked_rows") or 0) if int(todos.get("total") or 0) > 0 else 0

    async def _probe_all() -> tuple[dict, dict, dict]:
        return await asyncio.gather(
            asyncio.to_thread(probe_endpoint, config.LLM_BIG_ENDPOINT),
            asyncio.to_thread(probe_endpoint, config.LLM_FAST_ENDPOINT),
            asyncio.to_thread(probe_endpoint, config.LLM_EMBED_ENDPOINT),
        )

    big, fast, embed = asyncio.run(_probe_all())
    stage = 2 if fast.get("ok") else 1
    active_metrics = metrics_svc.list_metrics(status="active")
    biz = business_snapshot(top_n=5)
    return {
        "tables": tables,
        "dim_material": tables.get("dim_material", 0),
        "business": biz,
        "quality": quality,
        "estimated_releasable_rows": estimated_releasable,
        "todos": todos,
        "next_action": next_action,
        "flow": {
            "published_total": flow.get("published_total"),
            "published_by_level": flow.get("published_by_level"),
            "l1_ratio": flow.get("l1_ratio"),
            "pending": flow_pending,
        },
        "gate": {
            "ready": gate.get("ready"),
            "missing": gate.get("missing"),
        },
        "recent_files": recent_files,
        "metrics_active": [
            {
                "metric_id": m.get("metric_id"),
                "metric_name": m.get("metric_name"),
                "status": m.get("status"),
                "unit": m.get("unit"),
                "version": m.get("version"),
                "metric_group": m.get("metric_group") or "business",
            }
            for m in (active_metrics.get("items") or [])
        ],
        "models": {
            "stage": stage,
            "big": {"ok": bool(big.get("ok")), "configured_model": config.LLM_BIG_MODEL},
            "fast": {
                "ok": bool(fast.get("ok")),
                "configured_model": config.LLM_FAST_MODEL,
                "note": "Stage 2+ (7B transition ok)",
            },
            "embed": {
                "ok": bool(embed.get("ok")),
                "configured_model": config.LLM_EMBED_MODEL,
            },
        },
    }
