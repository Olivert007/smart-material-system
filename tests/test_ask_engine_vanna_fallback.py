# -*- coding: utf-8 -*-
"""Step2: VannaEngine with legacy fallback (docs/19)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_vanna_fb_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ASK_ENGINE"] = "vanna"
os.environ["LLM_BIG_ENDPOINT"] = ""
os.environ["LLM_FAST_ENDPOINT"] = ""
os.environ["VANNA_PERSIST_DIR"] = str(TMP / "vanna")

sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.repositories import writer_conn  # noqa: E402
from app.repositories.db import init_meta  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.llm.model_client import LlmResult  # noqa: E402
from app.services.metrics import ensure_metrics_seed  # noqa: E402
from app.services.query.ask_engine import AskEngineResult, get_ask_engine  # noqa: E402
from app.services.query.vanna_engine import VannaEngine  # noqa: E402
from app.services.query.vanna_local import reset_sms_vanna  # noqa: E402
from app.services.text2sql import ask  # noqa: E402


@pytest.fixture(autouse=True)
def _vanna_mode(monkeypatch):
    monkeypatch.setenv("ASK_ENGINE", "vanna")
    monkeypatch.setattr(config, "ASK_ENGINE", "vanna")
    reset_sms_vanna()


@pytest.fixture(autouse=True)
def _fresh_db():
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()
    ensure_metrics_seed()


def test_get_ask_engine_vanna_mode():
    engine = get_ask_engine()
    assert isinstance(engine, VannaEngine)


def test_vanna_success_returns_vanna_source(monkeypatch):
    def fake_generate(self, question, **kwargs):
        return "SELECT COUNT(*) AS n FROM fact_inventory LIMIT 10"

    monkeypatch.setattr(
        "app.services.query.vanna_engine.get_sms_vanna",
        lambda: type("VN", (), {"generate_sql": fake_generate})(),
    )
    engine = VannaEngine()
    gen = engine.generate_sql("库存表有多少行")
    assert gen.ok is True
    assert gen.source == "vanna"
    assert gen.engine_state == "sql_generated"
    assert "fact_inventory" in (gen.sql or "")


def test_vanna_failure_falls_back_to_legacy(monkeypatch):
    import app.services.query.legacy_text2sql_engine as leg

    def boom(*args, **kwargs):
        raise RuntimeError("vanna down")

    def legacy_chat(**kwargs):
        return LlmResult(
            ok=True,
            text="SELECT COUNT(*) AS n FROM fact_inventory",
            model="test-big",
            model_invoked=True,
            output_available=True,
            model_state="llm_analysis_available",
            latency_ms=12,
        )

    monkeypatch.setattr("app.services.query.vanna_engine.get_sms_vanna", lambda: (_ for _ in ()).throw(RuntimeError("vanna down")))
    monkeypatch.setattr(leg, "chat", legacy_chat)
    gen = VannaEngine().generate_sql("库存表有多少行")
    assert gen.ok is True
    assert gen.source == "llm_text2sql"
    assert gen.engine_fallback is True
    assert gen.fallback_reason == "vanna_failed"


def test_vanna_guard_fail_falls_back(monkeypatch):
    import app.services.query.legacy_text2sql_engine as leg

    def bad_sql(self, question, **kwargs):
        return "DROP TABLE fact_inventory"

    def legacy_chat(**kwargs):
        return LlmResult(
            ok=True,
            text="SELECT 1 AS n",
            model="test-big",
            model_invoked=True,
            output_available=True,
            model_state="llm_analysis_available",
        )

    monkeypatch.setattr(
        "app.services.query.vanna_engine.get_sms_vanna",
        lambda: type("VN", (), {"generate_sql": bad_sql})(),
    )
    monkeypatch.setattr(leg, "chat", legacy_chat)
    gen = VannaEngine().generate_sql("测试")
    assert gen.engine_fallback is True
    assert gen.fallback_reason == "vanna_guard_failed"
    assert gen.ok is True
    assert gen.sql == "SELECT 1 AS n"


def test_ask_endpoint_vanna_fallback_hint(monkeypatch):
    import app.services.query.legacy_text2sql_engine as leg

    monkeypatch.setattr(
        "app.services.query.vanna_engine.get_sms_vanna",
        lambda: (_ for _ in ()).throw(RuntimeError("no vanna")),
    )

    def legacy_chat(**kwargs):
        return LlmResult(
            ok=False,
            model_state="local_model_unavailable",
            error="no healthy endpoint",
            model_request_attempted=True,
        )

    monkeypatch.setattr(leg, "chat", legacy_chat)
    res = ask("按库位统计库存记录数，取前10")
    assert res["ok"] is False
    assert res.get("engine_fallback") is True
    assert res.get("hint") and "回退" in res["hint"]
