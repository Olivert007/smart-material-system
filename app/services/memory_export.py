# -*- coding: utf-8 -*-
"""Export governance memory from meta.sqlite to readable Markdown snapshots.

Markdown files under data/memory/ are readable copies only; meta.sqlite remains
the source of truth. No EverOS / LanceDB / LLM calls.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app import config
from app.repositories import meta_conn

MEMORY_FILES = (
    "mapping.md",
    "sql-fewshot.md",
    "metrics.md",
    "ask-log-summary.md",
    "llm-call-summary.md",
)

_EMPTY = "暂无数据"
_ASK_LIMIT = 50
_LLM_LIMIT = 50


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("|", "\\|").replace("\n", " ")


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    if not rows:
        empty_row = "| " + " | ".join([_EMPTY] + [""] * (len(headers) - 1)) + " |"
        return "\n".join([head, sep, empty_row])
    body = ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        [name],
    ).fetchone()
    return row is not None


def _safe_query(con: sqlite3.Connection, table: str, sql: str, params: list[Any] | None = None):
    if not _table_exists(con, table):
        return []
    try:
        return con.execute(sql, params or []).fetchall()
    except sqlite3.Error:
        return []


def _write_mapping(con: sqlite3.Connection, path: Path) -> None:
    rows = _safe_query(
        con,
        "rule_dict",
        """
        SELECT header, business_domain, std_field, hits, source, confirmed_by, status
        FROM rule_dict
        ORDER BY updated_at DESC, rule_id DESC
        """,
    )
    lines = [
        "# 字段映射记忆（rule_dict）",
        "",
        "来源：meta.sqlite · rule_dict。人工确认后的表头→标准字段映射。",
        "",
    ]
    if not rows:
        lines.append(_EMPTY)
    else:
        lines.append(
            _md_table(
                ["表头", "业务域", "标准字段", "命中次数", "来源", "确认人", "状态"],
                [
                    [
                        r["header"],
                        r["business_domain"],
                        r["std_field"],
                        r["hits"],
                        r["source"],
                        r["confirmed_by"],
                        r["status"],
                    ]
                    for r in rows
                ],
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_metrics(con: sqlite3.Connection, path: Path) -> None:
    rows = _safe_query(
        con,
        "metric_dict",
        """
        SELECT metric_id, metric_name, status, definition_sql, unit, aliases
        FROM metric_dict
        ORDER BY metric_id
        """,
    )
    lines = [
        "# 指标口径（metric_dict）",
        "",
        "来源：meta.sqlite · metric_dict。",
        "",
    ]
    if not rows:
        lines.append(_EMPTY)
    else:
        lines.append(
            _md_table(
                ["指标 ID", "指标名称", "状态", "SQL 口径", "单位", "别名"],
                [
                    [
                        r["metric_id"],
                        r["metric_name"],
                        r["status"],
                        r["definition_sql"],
                        r["unit"],
                        r["aliases"],
                    ]
                    for r in rows
                ],
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_sql_fewshot(con: sqlite3.Connection, path: Path) -> None:
    rows = _safe_query(
        con,
        "sql_fewshot",
        """
        SELECT question, question_type, sql_gold, source, hits
        FROM sql_fewshot
        ORDER BY updated_at DESC
        """,
    )
    lines = [
        "# 问数样例（sql_fewshot）",
        "",
        "来源：meta.sqlite · sql_fewshot。",
        "",
    ]
    if not rows:
        lines.append(_EMPTY)
    else:
        lines.append(
            _md_table(
                ["问题", "问题类型", "SQL", "来源", "命中次数"],
                [
                    [
                        r["question"],
                        r["question_type"],
                        r["sql_gold"],
                        r["source"],
                        r["hits"],
                    ]
                    for r in rows
                ],
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_ask_log(con: sqlite3.Connection, path: Path) -> None:
    rows = _safe_query(
        con,
        "ask_log",
        """
        SELECT question, ok, source, error, created_at
        FROM ask_log
        ORDER BY created_at DESC, log_id DESC
        LIMIT ?
        """,
        [_ASK_LIMIT],
    )
    lines = [
        "# 问数历史摘要（ask_log）",
        "",
        f"来源：meta.sqlite · ask_log（最近 {_ASK_LIMIT} 条；不含完整结果集）。",
        "",
    ]
    if not rows:
        lines.append(_EMPTY)
    else:
        lines.append(
            _md_table(
                ["问题", "成功", "来源", "错误摘要", "时间"],
                [
                    [
                        r["question"],
                        "是" if r["ok"] else "否",
                        r["source"],
                        (r["error"] or "")[:200],
                        r["created_at"],
                    ]
                    for r in rows
                ],
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_llm_call(con: sqlite3.Connection, path: Path) -> None:
    rows = _safe_query(
        con,
        "llm_call",
        """
        SELECT role, model, task_type, ok, error, latency_ms, created_at
        FROM llm_call
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [_LLM_LIMIT],
    )
    lines = [
        "# 模型调用摘要（llm_call）",
        "",
        f"来源：meta.sqlite · llm_call（最近 {_LLM_LIMIT} 次；不含完整 prompt）。",
        "",
    ]
    if not rows:
        lines.append(_EMPTY)
    else:
        lines.append(
            _md_table(
                ["role", "model", "task_type", "ok", "error 摘要", "latency_ms", "时间"],
                [
                    [
                        r["role"],
                        r["model"],
                        r["task_type"],
                        r["ok"],
                        (r["error"] or "")[:200],
                        r["latency_ms"],
                        r["created_at"],
                    ]
                    for r in rows
                ],
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def export_memory_markdown(output_dir: str | Path | None = None) -> dict:
    """Export governance assets from meta.sqlite to Markdown under data/memory/."""
    out = Path(output_dir) if output_dir is not None else Path(config.DATA) / "memory"
    out.mkdir(parents=True, exist_ok=True)

    con = meta_conn()
    try:
        _write_mapping(con, out / "mapping.md")
        _write_sql_fewshot(con, out / "sql-fewshot.md")
        _write_metrics(con, out / "metrics.md")
        _write_ask_log(con, out / "ask-log-summary.md")
        _write_llm_call(con, out / "llm-call-summary.md")
    finally:
        con.close()

    return {
        "ok": True,
        "output_dir": str(out),
        "files": list(MEMORY_FILES),
    }
