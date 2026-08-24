# -*- coding: utf-8 -*-
"""Step1: AskEngine abstraction with legacy backend (docs/19)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_ask_engine_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ASK_ENGINE"] = "legacy"
os.environ["LLM_BIG_ENDPOINT"] = ""
os.environ["LLM_FAST_ENDPOINT"] = ""

sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.repositories import writer_conn  # noqa: E402
from app.repositories.db import init_meta  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.llm.model_client import LlmResult  # noqa: E402
from app.services.metrics import ensure_metrics_seed  # noqa: E402
from app.services.query.ask_engine import get_ask_engine  # noqa: E402
from app.services.query.legacy_text2sql_engine import LegacyText2SqlEngine, extract_sql  # noqa: E402
from app.services.text2sql import ask  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()
    ensure_metrics_seed()


def test_ask_engine_default_is_legacy():
    assert config.ASK_ENGINE == "legacy"
    engine = get_ask_engine()
    assert isinstance(engine, LegacyText2SqlEngine)


def test_extract_sql_strips_markdown_fence():
    raw = "说明\n```sql\nSELECT COUNT(*) FROM fact_inventory\n```"
    assert "SELECT COUNT(*) FROM fact_inventory" in extract_sql(raw)


def test_legacy_engine_degraded_when_model_down(monkeypatch):
    import app.services.query.legacy_text2sql_engine as leg

    def fake_chat(**kwargs):
        return LlmResult(
            ok=False,
            model_state="local_model_unavailable",
            error="no healthy endpoint",
            model_request_attempted=True,
        )

    monkeypatch.setattr(leg, "chat", fake_chat)
    gen = LegacyText2SqlEngine().generate_sql("按库位统计库存记录数")
    assert gen.ok is False
    assert gen.engine_state == "engine_failed"
    assert gen.source == "llm_text2sql"


def test_ask_uses_engine_but_metric_still_template_first(monkeypatch):
    import app.services.query.legacy_text2sql_engine as leg

    def boom(**kwargs):
        raise AssertionError("LLM should not run for metric template hit")

    monkeypatch.setattr(leg, "chat", boom)
    res = ask("库存总数量是多少")
    assert res["ok"] is True
    assert res["source"] == "metric_template"
    assert res["model_invoked"] is False


def test_ask_complex_question_degraded_via_engine(monkeypatch):
    import app.services.query.legacy_text2sql_engine as leg

    def fake_chat(**kwargs):
        return LlmResult(
            ok=False,
            model_state="local_model_unavailable",
            error="no healthy endpoint",
            model_request_attempted=True,
        )

    monkeypatch.setattr(leg, "chat", fake_chat)
    res = ask("按库位统计库存记录数，取前10")
    assert res["ok"] is False
    assert res["degraded"] is True
    assert res["source"] == "llm_text2sql"
    assert res.get("engine_state") == "engine_failed"
