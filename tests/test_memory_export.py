# -*- coding: utf-8 -*-
"""docs/20 Step3: memory Markdown export from meta.sqlite."""
from __future__ import annotations

from pathlib import Path

from app.repositories import init_meta, meta_tx
from app.services.memory_export import MEMORY_FILES, export_memory_markdown


def _seed_samples() -> None:
    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO rule_dict
              (header, std_field, business_domain, hits, source, confirmed_by, status)
            VALUES ('物资名称', 'item_name', 'inventory', 3, 'human_confirm', 'tester', 'active')
            """
        )
        con.execute(
            """
            INSERT INTO sql_fewshot
              (fewshot_id, question_type, question, sql_gold, hits, source, confirmed_by)
            VALUES (
              'fs-mem-1', 'count', '库存总数量是多少',
              'SELECT SUM(stock_qty) FROM fact_inventory', 2, 'seed', 'tester'
            )
            """
        )
        con.execute(
            """
            INSERT INTO metric_dict
              (metric_id, metric_name, aliases, unit, definition, definition_sql, status)
            VALUES (
              'MEM_TEST_QTY', '测试库存数量', '["库存数"]', '件',
              '测试指标', 'SELECT SUM(stock_qty) AS v FROM fact_inventory', 'draft'
            )
            """
        )
        con.execute(
            """
            INSERT INTO ask_log (question, sql, source, ok, error, latency_ms, rows)
            VALUES (
              '库存总数量是多少',
              'SELECT SUM(stock_qty) FROM fact_inventory',
              'metric_template', 1, NULL, 12, 1
            )
            """
        )
        con.execute(
            """
            INSERT INTO llm_call
              (call_id, role, endpoint, model, task_type, ok, latency_ms, error)
            VALUES (
              'llm-mem-1', 'fast', 'http://127.0.0.1:8000/v1', 'qwen2.5-7b',
              'map_suggest', 1, 88, NULL
            )
            """
        )


def test_export_memory_markdown_writes_five_files(tmp_path: Path):
    init_meta()
    _seed_samples()
    out_dir = tmp_path / "memory"
    result = export_memory_markdown(out_dir)

    assert result["ok"] is True
    assert result["files"] == list(MEMORY_FILES)
    for name in MEMORY_FILES:
        path = out_dir / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert text.strip(), name

    mapping = (out_dir / "mapping.md").read_text(encoding="utf-8")
    assert "物资名称" in mapping
    assert "item_name" in mapping

    fewshot = (out_dir / "sql-fewshot.md").read_text(encoding="utf-8")
    assert "库存总数量是多少" in fewshot

    metrics = (out_dir / "metrics.md").read_text(encoding="utf-8")
    assert "MEM_TEST_QTY" in metrics
    assert "测试库存数量" in metrics

    ask = (out_dir / "ask-log-summary.md").read_text(encoding="utf-8")
    assert "库存总数量是多少" in ask
    assert "metric_template" in ask

    llm = (out_dir / "llm-call-summary.md").read_text(encoding="utf-8")
    assert "map_suggest" in llm
    assert "qwen2.5-7b" in llm


def test_export_memory_markdown_empty_tables(tmp_path: Path):
    init_meta()
    out_dir = tmp_path / "memory-empty"
    result = export_memory_markdown(out_dir)
    assert result["ok"] is True
    for name in MEMORY_FILES:
        text = (out_dir / name).read_text(encoding="utf-8")
        assert "暂无数据" in text
