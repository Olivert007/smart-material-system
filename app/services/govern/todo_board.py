# -*- coding: utf-8 -*-
"""Unified govern todo board (optv1 02/08): read-only aggregation."""
from __future__ import annotations

import json
import re
from typing import Any

from app.repositories import meta_conn
from app.services import flow_gov as flow_gov_svc
from app.services import metrics as metrics_svc

_UNIT_RE = re.compile(r"(单位|计量|unit|uom|qty_unit|包装)", re.I)

# Types that belong on the AI suggestion review board (optv1/03).
_AI_REVIEW_TYPES = frozenset({"map", "unit", "master", "material_align", "flow"})

_GATE_ZH = {
    "rule_path_has_published_rows": "当前没有已发布的出入库流水，库存对账相关指标暂不可用",
    "QUALITY_BLOCKING": "部分记录未通过质量门禁，请先处理阻塞问题",
    "NO_COLUMNS": "部分工作表没有识别到可用字段，需要确认是否跳过或补充映射",
    "MAP_PENDING": "仍有字段映射需要人工确认",
    "missing_required_field": "缺少必填字段",
    "low_confidence_map": "字段映射置信度低，需人工确认",
    "unit_unresolved": "单位无法换算",
    "material_unmatched": "物资无法匹配",
    "quantity_anomaly": "数量异常",
}


def gate_label(code: str | None) -> str:
    if not code:
        return "-"
    return _GATE_ZH.get(code, code)


def _suggestion_meta(todo_type: str, *, raw_ref: dict[str, Any] | None = None) -> dict[str, Any]:
    """Annotate whether an item is rule judgment vs model suggestion (optv1/03)."""
    t = todo_type or ""
    raw = raw_ref or {}
    if t in ("exception", "release_blocker"):
        kind = "exception" if t == "exception" else "other"
        return {
            "suggestion_source": "system",
            "suggestion_kind": kind,
            "review_status": "pending",
            "source_label": "系统规则判断",
            "kind_label": "异常" if kind == "exception" else "其他",
        }
    if t in ("map", "unit"):
        return {
            "suggestion_source": "hybrid",
            "suggestion_kind": "field",
            "review_status": "pending",
            "source_label": "规则+模型候选",
            "kind_label": "字段" if t == "map" else "单位",
        }
    if t == "master":
        return {
            "suggestion_source": "model",
            "suggestion_kind": "material",
            "review_status": "pending",
            "source_label": "模型建议",
            "kind_label": "物资",
        }
    if t == "material_align":
        return {
            "suggestion_source": "model",
            "suggestion_kind": "classify",
            "review_status": "pending",
            "source_label": "模型建议",
            "kind_label": "分类/对齐",
        }
    if t == "flow":
        has_llm = bool(raw.get("llm_state")) and str(raw.get("llm_state")) not in (
            "",
            "skipped",
            "none",
        )
        return {
            "suggestion_source": "model" if has_llm else "hybrid",
            "suggestion_kind": "flow",
            "review_status": "pending",
            "source_label": "模型建议" if has_llm else "规则+模型候选",
            "kind_label": "出入库",
        }
    return {
        "suggestion_source": "system",
        "suggestion_kind": "other",
        "review_status": "pending",
        "source_label": "系统规则判断",
        "kind_label": "其他",
    }


def _enrich_item(item: dict[str, Any]) -> dict[str, Any]:
    meta = _suggestion_meta(
        str(item.get("todo_type") or ""),
        raw_ref=item.get("raw_ref") if isinstance(item.get("raw_ref"), dict) else None,
    )
    out = {**item, **meta}
    if out.get("requires_review"):
        out.setdefault("review_label", "待审核")
    return out
    return _GATE_ZH.get(str(code), str(code))


def _count(sql: str, params: list[Any] | None = None) -> int:
    con = meta_conn()
    try:
        row = con.execute(sql, params or []).fetchall()
        if not row:
            return 0
        return int(row[0][0])
    except Exception:
        return 0
    finally:
        con.close()


def _blocked_rows() -> int:
    con = meta_conn()
    try:
        row = con.execute(
            """
            SELECT COALESCE(SUM(s.blocked_rows), 0)
            FROM staging_record s
            INNER JOIN (
              SELECT file_id, MAX(updated_at) AS max_updated
              FROM staging_record
              GROUP BY file_id
            ) latest
              ON s.file_id = latest.file_id AND s.updated_at = latest.max_updated
            """
        ).fetchone()
        return int(row[0] if row else 0)
    except Exception:
        try:
            row = con.execute(
                "SELECT COALESCE(SUM(blocked_rows), 0) FROM staging_record"
            ).fetchone()
            return int(row[0] if row else 0)
        except Exception:
            return 0
    finally:
        con.close()


def _file_count() -> int:
    return _count("SELECT COUNT(*) FROM file_batch")


def _staging_count() -> int:
    return _count("SELECT COUNT(*) FROM staging_record")


def _active_intake_tasks() -> int:
    return _count(
        """
        SELECT COUNT(*) FROM intake_task
        WHERE lower(COALESCE(status,'')) IN ('pending','queued','running','processing','started')
        """
    )


def _release_count() -> int:
    return _count("SELECT COUNT(*) FROM release_record")


def _is_unit_field(header: str | None, suggested: str | None) -> bool:
    text = f"{header or ''} {suggested or ''}"
    return bool(_UNIT_RE.search(text))


def _top_score_from_candidates(raw: Any) -> float | None:
    """Parse candidates_json / list and return top score if present."""
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            return None
    if not isinstance(data, list) or not data:
        return None
    best: float | None = None
    for c in data:
        if not isinstance(c, dict):
            continue
        sc = c.get("score")
        if sc is None:
            continue
        try:
            v = float(sc)
        except (TypeError, ValueError):
            continue
        if best is None or v > best:
            best = v
    return best


def _file_name_map(con) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for r in con.execute("SELECT file_id, filename FROM file_batch").fetchall():
            d = dict(r)
            fid = d.get("file_id")
            if fid:
                out[str(fid)] = str(d.get("filename") or fid)
    except Exception:
        pass
    return out


def _resolve_source_file(
    value: str | None, names: dict[str, str]
) -> tuple[str | None, str | None]:
    """Return (display_name, file_id)."""
    if not value:
        return None, None
    s = str(value)
    if s in names:
        return names[s], s
    for fid, name in names.items():
        if name == s:
            return name, fid
    return s, s


def _derive_state(
    *,
    file_count: int,
    blocked: int,
    release_blockers: int,
    pending_total: int,
    staging_count: int = 0,
    active_tasks: int = 0,
    release_count: int = 0,
) -> tuple[str, str]:
    if file_count <= 0:
        return (
            "no_data",
            "当前没有可规整数据。请先在「数据接入」上传原始需求表或台账文件。",
        )
    # 有文件但尚无规整暂存，或仅有进行中任务且还没有任何 staging
    if staging_count <= 0:
        return (
            "parsing",
            "正在识别结构或生成规整结果。请到「数据接入」查看进度，完成后回到本页处理待办。",
        )
    if blocked > 0 or release_blockers > 0:
        return (
            "blocked",
            "当前数据暂不可用：部分记录未通过质量门禁或存在发布阻断，请先处理字段、物资、单位或异常问题。",
        )
    if pending_total > 0:
        return (
            "needs_standardization",
            "当前需要继续规整：仍有待确认事项，确认后才会进入可用数据。",
        )
    if release_count > 0:
        return (
            "published",
            "当前已有写入业务库的发布版本（可用候选）。不等于正式发布报表；可查看数据成果或追溯审计。",
        )
    return (
        "ready",
        "当前数据可用（可用候选）。不等于正式发布报表；可查看数据成果或追溯审计。",
    )


def _empty_reason(*, total_todos: int, file_count: int, blocked: int, gate_ready: bool | None) -> str | None:
    if file_count <= 0:
        return "当前没有治理待办，因为还没有接入可规整数据。"
    if total_todos <= 0 and blocked <= 0 and gate_ready:
        return "当前没有治理待办，最近一次规整已通过门禁。"
    if total_todos <= 0 and blocked <= 0:
        return "当前没有待确认事项；若问数或报表异常，请检查数据成果与追溯审计。"
    return None


def estimated_releasable_rows(*, blocked: int | None = None) -> int:
    """Estimate how many blocked/pending rows could become available after handling open todos.

    Uses sum of todo affected_rows, capped by current blocked_rows (when known).
    """
    blocked_n = int(blocked if blocked is not None else _blocked_rows())
    try:
        board = todo_list(limit=500, offset=0, todo_type=None)
    except Exception:
        return max(0, blocked_n)
    total_affected = 0
    for it in board.get("items") or []:
        t = str(it.get("todo_type") or "")
        if t == "release_blocker":
            continue
        total_affected += max(0, int(it.get("affected_rows") or 0))
    if blocked_n > 0:
        return min(total_affected, blocked_n) if total_affected > 0 else blocked_n
    return total_affected


def todo_summary() -> dict[str, Any]:
    flow = flow_gov_svc.parse_stats()
    flow_pending = int(flow.get("pending") or 0)
    map_pending = _count("SELECT COUNT(*) FROM map_pending WHERE status='pending'")
    unit_pending = _count(
        """
        SELECT COUNT(*) FROM map_pending
        WHERE status='pending'
          AND (
            lower(COALESCE(header,'')) LIKE '%unit%'
            OR header LIKE '%单位%'
            OR header LIKE '%计量%'
            OR lower(COALESCE(suggested_field,'')) LIKE '%unit%'
            OR COALESCE(suggested_field,'') LIKE '%单位%'
          )
        """
    )
    master_pending = _count("SELECT COUNT(*) FROM master_pending WHERE status='pending'")
    material_align = _count("SELECT COUNT(*) FROM material_align WHERE status='proposed'")
    rule_learn = _count(
        "SELECT COUNT(*) FROM govern_confirm WHERE source='rule_learn' AND decision='proposed'"
    )
    corrections = _count(
        "SELECT COUNT(*) FROM correction_request WHERE status='proposed'"
    )
    exception_groups = _count(
        """
        SELECT COUNT(*) FROM (
          SELECT reason_code, file_id FROM staging_blocked GROUP BY reason_code, file_id
        )
        """
    )
    blocked = _blocked_rows()
    gate = metrics_svc.flow_activation_gate()
    gate_ready = gate.get("ready")
    release_blockers = len(gate.get("missing") or []) if gate_ready is False else 0
    file_count = _file_count()
    staging_count = _staging_count()
    active_tasks = _active_intake_tasks()
    release_count = _release_count()
    pending_core = (
        map_pending
        + master_pending
        + flow_pending
        + material_align
        + corrections
        + exception_groups
    )
    total = pending_core + release_blockers
    state, state_message = _derive_state(
        file_count=file_count,
        blocked=blocked,
        release_blockers=release_blockers,
        pending_total=pending_core,
        staging_count=staging_count,
        active_tasks=active_tasks,
        release_count=release_count,
    )

    next_actions: list[dict[str, str]] = []
    if file_count <= 0:
        next_actions.append(
            {"code": "intake", "label": "去数据接入", "path": "/intake"}
        )
    elif state == "parsing":
        next_actions.append(
            {"code": "intake", "label": "查看接入进度", "path": "/intake"}
        )
    elif release_blockers > 0:
        next_actions.append(
            {"code": "gate", "label": "处理发布阻断项", "path": "/govern?type=release_blocker"}
        )
    elif map_pending + master_pending + material_align + flow_pending > 0:
        next_actions.append(
            {
                "code": "ai_review",
                "label": "审核 AI 建议",
                "path": "/govern?tab=map",
            }
        )
    elif exception_groups > 0 or blocked > 0:
        next_actions.append(
            {"code": "exception", "label": "查看阻塞异常", "path": "/govern?type=exception"}
        )
    else:
        next_actions.append(
            {"code": "data", "label": "查看数据成果", "path": "/data"}
        )
        next_actions.append(
            {"code": "trace", "label": "查看追溯审计", "path": "/trace"}
        )

    # Keep AI review reachable even when a higher-priority CTA is primary.
    ai_pending = map_pending + master_pending + material_align + flow_pending
    if ai_pending > 0 and not any(a.get("code") == "ai_review" for a in next_actions):
        next_actions.append(
            {"code": "ai_review", "label": "审核 AI 建议", "path": "/govern?tab=map"}
        )

    releasable = estimated_releasable_rows(blocked=blocked)

    return {
        "state": state,
        "state_message": state_message,
        "map_pending_count": map_pending,
        "unit_pending_count": unit_pending,
        "material_pending_count": master_pending + material_align,
        "master_pending_count": master_pending,
        "material_align_count": material_align,
        "flow_pending_count": flow_pending,
        "exception_pending_count": exception_groups,
        "ai_suggestion_pending_count": (
            map_pending + master_pending + material_align + flow_pending
        ),
        "rule_conflict_count": rule_learn,
        "correction_count": corrections,
        "release_blocker_count": release_blockers,
        "blocked_rows": blocked,
        "estimated_releasable_rows": releasable,
        "file_count": file_count,
        "staging_count": staging_count,
        "release_count": release_count,
        "total": total,
        "gate": {"ready": gate_ready, "missing": gate.get("missing") or []},
        "empty_reason": _empty_reason(
            total_todos=total,
            file_count=file_count,
            blocked=blocked,
            gate_ready=bool(gate_ready),
        ),
        "next_actions": next_actions,
    }


def _priority(todo_type: str, affected: int, critical: bool) -> tuple[int, int, int]:
    type_w = {
        "release_blocker": 0,
        "exception": 1,
        "map": 2,
        "unit": 3,
        "master": 4,
        "material_align": 5,
        "flow": 6,
        "correction": 7,
    }.get(todo_type, 9)
    return (0 if critical else 1, -int(affected or 0), type_w)


def _map_affected(con, header: str | None, file_id: str | None) -> int:
    """Best-effort: count blocked rows sharing same header, else 1."""
    try:
        if header and file_id:
            row = con.execute(
                "SELECT COUNT(*) AS c FROM staging_blocked WHERE file_id=? AND header=?",
                [file_id, header],
            ).fetchone()
            n = int(row[0] if row else 0)
            if n > 0:
                return n
        if header:
            row = con.execute(
                "SELECT COUNT(*) AS c FROM staging_blocked WHERE header=?",
                [header],
            ).fetchone()
            n = int(row[0] if row else 0)
            if n > 0:
                return n
    except Exception:
        pass
    return 1


def todo_list(*, limit: int = 50, offset: int = 0, todo_type: str | None = None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    con = meta_conn()
    try:
        names = _file_name_map(con)
        gate = metrics_svc.flow_activation_gate()
        if gate.get("ready") is False:
            for m in gate.get("missing") or []:
                items.append(
                    {
                        "todo_id": f"gate:{m}",
                        "todo_type": "release_blocker",
                        "title": f"发布阻断：{gate_label(m)}",
                        "status": "pending",
                        "priority": "high",
                        "affected_rows": 0,
                        "source_file": None,
                        "source_sheet": None,
                        "suggestion": "完成相关规整或发布流水后再启用受影响指标",
                        "confidence": None,
                        "actions": ["view"],
                        "requires_review": True,
                        "forms_rule": False,
                        "version": None,
                        "raw_ref": {"code": m, "label": gate_label(m)},
                    }
                )

        try:
            for r in con.execute(
                """
                SELECT reason_code,
                       file_id,
                       COUNT(*) AS cnt,
                       MAX(header) AS header
                FROM staging_blocked
                GROUP BY reason_code, file_id
                ORDER BY cnt DESC
                LIMIT 80
                """
            ).fetchall():
                d = dict(r)
                code = d.get("reason_code") or "exception"
                cnt = int(d.get("cnt") or 0)
                fid = d.get("file_id")
                display, file_id = _resolve_source_file(fid, names)
                items.append(
                    {
                        "todo_id": f"exception:{code}:{fid or '_'}",
                        "todo_type": "exception",
                        "title": f"异常：{gate_label(str(code))}（{cnt} 行）",
                        "status": "pending",
                        "priority": "high",
                        "affected_rows": cnt,
                        "source_file": display,
                        "source_sheet": None,
                        "suggestion": "请到处理详情或数据成果「阻塞数据」查看明细；忽略不等于修复",
                        "confidence": None,
                        "actions": ["view"],
                        "requires_review": True,
                        "forms_rule": False,
                        "version": None,
                        "raw_ref": {
                            "reason_code": code,
                            "header": d.get("header"),
                            "count": cnt,
                            "file_id": file_id or fid,
                        },
                    }
                )
        except Exception:
            pass

        for r in con.execute(
            """
            SELECT pending_id, file_id, sheet, header, suggested_field, reason, status,
                   version, candidates_json
            FROM map_pending WHERE status='pending'
            ORDER BY updated_at DESC LIMIT 200
            """
        ).fetchall():
            d = dict(r)
            unitish = _is_unit_field(d.get("header"), d.get("suggested_field"))
            ttype = "unit" if unitish else "map"
            affected = _map_affected(con, d.get("header"), d.get("file_id"))
            display, file_id = _resolve_source_file(d.get("file_id"), names)
            conf = _top_score_from_candidates(d.get("candidates_json"))
            raw = {k: v for k, v in d.items() if k != "candidates_json"}
            raw["file_id"] = file_id or d.get("file_id")
            raw["from_value"] = d.get("header")
            raw["to_value"] = d.get("suggested_field")
            items.append(
                {
                    "todo_id": d["pending_id"],
                    "todo_type": ttype,
                    "title": (
                        f"单位待确认：{d.get('header') or '-'}"
                        if unitish
                        else f"字段待确认：{d.get('header') or '-'}"
                    ),
                    "status": d.get("status") or "pending",
                    "priority": "medium",
                    "affected_rows": affected,
                    "source_file": display,
                    "source_sheet": d.get("sheet"),
                    "suggestion": d.get("suggested_field")
                    or d.get("reason")
                    or ("请确认标准单位映射；无明确规则时不自动换算" if unitish else "请确认标准字段映射"),
                    "confidence": conf,
                    "actions": ["confirm", "reject", "view"],
                    "requires_review": True,
                    "forms_rule": True,
                    "version": int(d.get("version") or 1),
                    "raw_ref": raw,
                }
            )

        for r in con.execute(
            """
            SELECT pending_id, material_id, material_name, material_code, match_level,
                   source_file, status, conflict_type, version, candidates_json
            FROM master_pending WHERE status='pending'
            ORDER BY updated_at DESC LIMIT 200
            """
        ).fetchall():
            d = dict(r)
            display, file_id = _resolve_source_file(d.get("source_file"), names)
            conf = _top_score_from_candidates(d.get("candidates_json"))
            raw = {k: v for k, v in d.items() if k != "candidates_json"}
            raw["file_id"] = file_id
            raw["from_value"] = d.get("material_name")
            raw["to_value"] = d.get("material_code") or d.get("material_id")
            items.append(
                {
                    "todo_id": d["pending_id"],
                    "todo_type": "master",
                    "title": f"物资待匹配：{d.get('material_name') or d.get('material_id') or '-'}",
                    "status": "pending",
                    "priority": "medium",
                    "affected_rows": 1,
                    "source_file": display,
                    "source_sheet": None,
                    "suggestion": f"匹配级别 {d.get('match_level') or '-'}；系统不会自动创建主数据",
                    "confidence": conf,
                    "actions": ["confirm", "reject", "view"],
                    "requires_review": True,
                    "forms_rule": True,
                    "version": int(d.get("version") or 1),
                    "raw_ref": raw,
                }
            )

        for r in con.execute(
            """
            SELECT align_id, from_material_id, to_material_id, from_name, to_name, score, status, version
            FROM material_align WHERE status='proposed'
            ORDER BY updated_at DESC LIMIT 200
            """
        ).fetchall():
            d = dict(r)
            score = d.get("score")
            items.append(
                {
                    "todo_id": d["align_id"],
                    "todo_type": "material_align",
                    "title": f"物资对齐：{d.get('from_name') or d.get('from_material_id')} → {d.get('to_name') or d.get('to_material_id')}",
                    "status": "proposed",
                    "priority": "medium",
                    "affected_rows": 1,
                    "source_file": None,
                    "source_sheet": None,
                    "suggestion": "请人工确认是否合并；AI/相似度建议不能自动合并主数据",
                    "confidence": float(score) if score is not None else None,
                    "actions": ["confirm", "reject", "view"],
                    "requires_review": True,
                    "forms_rule": True,
                    "version": int(d.get("version") or 1),
                    "raw_ref": {
                        **d,
                        "from_value": d.get("from_name") or d.get("from_material_id"),
                        "to_value": d.get("to_name") or d.get("to_material_id"),
                    },
                }
            )

        # Flow: aggregate by file_id + source_sheet + flow_type
        try:
            flow_rows = con.execute(
                """
                SELECT file_id, source_sheet, flow_type,
                       COUNT(*) AS cnt,
                       MIN(pending_id) AS sample_pending_id,
                       MAX(text_raw) AS text_raw,
                       MAX(parse_level) AS parse_level
                FROM flow_pending WHERE status='pending'
                GROUP BY file_id, COALESCE(source_sheet, ''), COALESCE(flow_type, '')
                ORDER BY cnt DESC
                LIMIT 100
                """
            ).fetchall()
            for r in flow_rows:
                d = dict(r)
                cnt = int(d.get("cnt") or 0)
                display, file_id = _resolve_source_file(d.get("file_id"), names)
                sample_id = d.get("sample_pending_id")
                sample_version = 1
                try:
                    vrow = con.execute(
                        "SELECT version FROM flow_pending WHERE pending_id=?", [sample_id]
                    ).fetchone()
                    if vrow and vrow[0] is not None:
                        sample_version = int(vrow[0])
                except Exception:
                    pass
                text = (d.get("text_raw") or "")[:60]
                items.append(
                    {
                        "todo_id": sample_id,
                        "todo_type": "flow",
                        "title": (
                            f"出入库待确认：{d.get('flow_type') or ''} ×{cnt}"
                            + (f" · {text}" if text else "")
                        ),
                        "status": "pending",
                        "priority": "medium",
                        "affected_rows": cnt,
                        "source_file": display,
                        "source_sheet": d.get("source_sheet"),
                        "suggestion": (
                            f"解析级别 {d.get('parse_level') or '-'}；共 {cnt} 条待确认；"
                            "模型建议须人工确认"
                        ),
                        "confidence": None,
                        "actions": ["confirm", "ignore", "view"],
                        "requires_review": True,
                        "forms_rule": False,
                        "version": sample_version,
                        "raw_ref": {
                            "file_id": file_id or d.get("file_id"),
                            "source_sheet": d.get("source_sheet"),
                            "flow_type": d.get("flow_type"),
                            "count": cnt,
                            "sample_pending_id": sample_id,
                        },
                    }
                )
        except Exception:
            for r in con.execute(
                """
                SELECT pending_id, file_id, source_sheet, source_row, flow_type, text_raw,
                       parse_level, status, version, llm_state
                FROM flow_pending WHERE status='pending'
                ORDER BY updated_at DESC LIMIT 200
                """
            ).fetchall():
                d = dict(r)
                text = (d.get("text_raw") or "")[:80]
                display, file_id = _resolve_source_file(d.get("file_id"), names)
                raw = dict(d)
                raw["file_id"] = file_id or d.get("file_id")
                items.append(
                    {
                        "todo_id": d["pending_id"],
                        "todo_type": "flow",
                        "title": f"出入库待确认：{d.get('flow_type') or ''} {text}",
                        "status": "pending",
                        "priority": "medium",
                        "affected_rows": 1,
                        "source_file": display,
                        "source_sheet": d.get("source_sheet"),
                        "suggestion": f"解析级别 {d.get('parse_level') or '-'}；模型建议须人工确认",
                        "confidence": None,
                        "actions": ["confirm", "ignore", "view"],
                        "requires_review": True,
                        "forms_rule": False,
                        "version": int(d.get("version") or 1),
                        "raw_ref": raw,
                    }
                )
    finally:
        con.close()

    if todo_type in ("ai", "ai_review", "suggestion"):
        items = [i for i in items if i.get("todo_type") in _AI_REVIEW_TYPES]
    elif todo_type:
        items = [i for i in items if i.get("todo_type") == todo_type]

    items = [_enrich_item(i) for i in items]

    items.sort(
        key=lambda i: _priority(
            str(i.get("todo_type")),
            int(i.get("affected_rows") or 0),
            i.get("todo_type") == "release_blocker"
            or i.get("todo_type") == "exception"
            or i.get("priority") == "high",
        )
    )

    total = len(items)
    sliced = items[max(0, offset) : max(0, offset) + max(1, min(limit, 200))]
    return {"total": total, "limit": limit, "offset": offset, "items": sliced}


def lookup_todo(todo_id: str) -> dict[str, Any] | None:
    """Find a single todo by id from the aggregated board (for decision/dry_run)."""
    res = todo_list(limit=500, offset=0, todo_type=None)
    for it in res.get("items") or []:
        if str(it.get("todo_id")) == str(todo_id):
            return it
    return None


def _pending_still_open(todo_id: str, todo_type: str) -> bool:
    con = meta_conn()
    try:
        if todo_type in ("map", "unit"):
            row = con.execute(
                "SELECT status FROM map_pending WHERE pending_id=?", [todo_id]
            ).fetchone()
            return bool(row and row["status"] == "pending")
        if todo_type == "flow":
            row = con.execute(
                "SELECT status FROM flow_pending WHERE pending_id=?", [todo_id]
            ).fetchone()
            return bool(row and row["status"] in ("pending", "conflict"))
        if todo_type == "master":
            row = con.execute(
                "SELECT status FROM master_pending WHERE pending_id=?", [todo_id]
            ).fetchone()
            return bool(row and row["status"] == "pending")
        if todo_type == "material_align":
            row = con.execute(
                "SELECT status FROM material_align WHERE align_id=?", [todo_id]
            ).fetchone()
            return bool(row and row["status"] == "proposed")
        if todo_type in ("exception", "release_blocker"):
            return True
        return False
    except Exception:
        return False
    finally:
        con.close()


def _resolve_todo_type_from_db(todo_id: str) -> str | None:
    con = meta_conn()
    try:
        if con.execute(
            "SELECT 1 FROM map_pending WHERE pending_id=?", [todo_id]
        ).fetchone():
            return "map"
        if con.execute(
            "SELECT 1 FROM flow_pending WHERE pending_id=?", [todo_id]
        ).fetchone():
            return "flow"
        if con.execute(
            "SELECT 1 FROM master_pending WHERE pending_id=?", [todo_id]
        ).fetchone():
            return "master"
        if con.execute(
            "SELECT 1 FROM material_align WHERE align_id=?", [todo_id]
        ).fetchone():
            return "material_align"
    except Exception:
        return None
    finally:
        con.close()
    return None


def _todo_version(todo_id: str, todo_type: str) -> int | None:
    """Read current optimistic version for a DB-backed pending item (optv1/08)."""
    table: str | None = None
    key = "pending_id"
    if todo_type in ("map", "unit"):
        table = "map_pending"
    elif todo_type == "flow":
        table = "flow_pending"
    elif todo_type == "master":
        table = "master_pending"
    elif todo_type == "material_align":
        table = "material_align"
        key = "align_id"
    if table is None:
        return None
    con = meta_conn()
    try:
        row = con.execute(
            f"SELECT version FROM {table} WHERE {key}=?", [todo_id]
        ).fetchone()
        if not row:
            return None
        return int(row[0] or 1)
    except Exception:
        return None
    finally:
        con.close()


def decide_todo(
    *,
    todo_id: str,
    decision: str,
    actor: str,
    amended_value: dict[str, Any] | None = None,
    note: str = "",
    expected_version: int | None = None,
    idempotency_key: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Unified decision facade (optv1/08). Actor must be server-injected."""
    from app.services import idempotency as idem
    from app.services import map_gov as map_gov_svc
    from app.services import flow_gov as flow_gov_svc
    from app.services import master_gov as master_gov_svc
    from app.services import material_align as align_svc

    decision = (decision or "").strip().lower()
    if decision not in ("accept", "amend", "reject", "ignore", "approve", "merge"):
        raise ValueError("decision must be accept|amend|reject|ignore")

    scope = "govern_todo_decision"
    if idempotency_key and not dry_run:
        cached = idem.get(scope, idempotency_key)
        if cached:
            return {**cached, "idempotent": True, "idempotency_replay": True}

    item = lookup_todo(todo_id)
    if not item:
        ttype = None
        if str(todo_id).startswith("gate:"):
            ttype = "release_blocker"
        elif str(todo_id).startswith("exception:"):
            ttype = "exception"
        else:
            ttype = _resolve_todo_type_from_db(todo_id)
            if ttype:
                # exists in DB but not on pending board → already resolved
                raise RuntimeError("todo_conflict: pending already resolved")
        if ttype:
            item = {
                "todo_id": todo_id,
                "todo_type": ttype,
                "affected_rows": 0,
                "forms_rule": False,
                "suggestion": "",
            }
        else:
            raise KeyError("todo not found")

    todo_type = str(item.get("todo_type") or "")

    if expected_version is not None:
        current = _todo_version(todo_id, todo_type)
        if current is not None and int(current) != int(expected_version):
            raise RuntimeError(
                f"todo_conflict: version mismatch (expected {expected_version}, got {current})"
            )

    warning = None
    if decision == "ignore":
        warning = "忽略不等于修复"

    preview = {
        "ok": True,
        "dry_run": True,
        "todo_id": todo_id,
        "todo_type": todo_type,
        "decision": decision,
        "affected_rows": int(item.get("affected_rows") or 0),
        "forms_rule": bool(item.get("forms_rule")),
        "suggestion": item.get("suggestion") or "",
        "version": item.get("version"),
        "warning": warning,
    }
    if dry_run:
        return preview

    if todo_type in ("exception", "release_blocker"):
        raise ValueError(
            "该待办仅支持查看详情，不能通过统一决策直接忽略或采纳；请到处理详情或数据成果处理"
        )

    if not _pending_still_open(todo_id, todo_type):
        raise RuntimeError("todo_conflict: pending already resolved")

    result: dict[str, Any]
    if todo_type in ("map", "unit"):
        std_field = None
        if isinstance(amended_value, dict):
            std_field = amended_value.get("std_field") or amended_value.get("to")
        mapped = decision if decision in ("accept", "amend", "ignore") else (
            "ignore" if decision == "reject" else decision
        )
        result = map_gov_svc.confirm_pending(
            pending_id=todo_id,
            decision=mapped,
            std_field=str(std_field) if std_field else None,
            note=note,
            actor=actor,
        )
    elif todo_type == "flow":
        corrected = amended_value if isinstance(amended_value, dict) else None
        mapped = decision if decision in ("accept", "amend", "ignore") else (
            "ignore" if decision == "reject" else decision
        )
        result = flow_gov_svc.confirm_pending(
            pending_id=todo_id,
            decision=mapped,
            actor=actor,
            corrected=corrected,
            note=note,
        )
    elif todo_type == "master":
        mapped = {
            "accept": "approve",
            "approve": "approve",
            "reject": "reject",
            "ignore": "reject",
            "merge": "merge",
            "amend": "merge",
        }.get(decision, decision)
        merge_to = None
        if isinstance(amended_value, dict):
            merge_to = amended_value.get("merge_to_material_id") or amended_value.get("to")
        result = master_gov_svc.confirm_pending(
            pending_id=todo_id,
            decision=mapped,
            actor=actor,
            note=note,
            merge_to_material_id=str(merge_to) if merge_to else None,
        )
    elif todo_type == "material_align":
        mapped = "accept" if decision in ("accept", "approve") else "reject"
        result = align_svc.confirm_alignment(
            align_id=todo_id,
            decision=mapped,
            actor=actor,
            note=note,
        )
    else:
        raise ValueError(f"unsupported todo_type: {todo_type}")

    out = {
        "ok": True,
        "dry_run": False,
        "todo_id": todo_id,
        "todo_type": todo_type,
        "decision": decision,
        "affected_rows": int(item.get("affected_rows") or 0),
        "forms_rule": bool(item.get("forms_rule")),
        "version": item.get("version"),
        "warning": warning,
        "result": result,
        "actor": actor,
    }
    if idempotency_key:
        idem.put(scope, idempotency_key, out)
    return out
