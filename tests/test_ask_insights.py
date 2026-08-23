# -*- coding: utf-8 -*-
"""Ask assistant P0: recommendations, empty-result insight, new metric templates."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_ask_insights_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["LLM_BIG_ENDPOINT"] = ""
os.environ["LLM_FAST_ENDPOINT"] = ""

sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.repositories import writer_conn  # noqa: E402
from app.repositories.db import init_meta  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.metrics import ensure_metrics_seed, match_metrics  # noqa: E402
from app.services.query.ask_insights import (  # noqa: E402
    empty_result_insight,
    recommend_questions,
)
from app.services.text2sql import ask  # noqa: E402
from app.workers import intake_worker  # noqa: E402


@pytest.fixture(autouse=True)
def _disable_worker():
    orig = intake_worker.worker.start
    intake_worker.worker.start = lambda: None
    yield
    intake_worker.worker.start = orig


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _fresh_db():
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()
    ensure_metrics_seed()


def test_new_metric_templates_match():
    m = match_metrics("零库存物资有多少")
    assert m["best"] and m["best"]["metric_id"] == "INV_ZERO_STOCK_CNT"

    m2 = match_metrics("缺少库位的库存有多少")
    assert m2["best"]["metric_id"] == "INV_MISSING_LOCATION_CNT"

    m3 = match_metrics("缺少保管人的资产有多少")
    assert m3["best"]["metric_id"] == "ASSET_MISSING_MANAGER_CNT"


def test_recommend_questions_no_data():
    out = recommend_questions(model_available=True)
    assert out["data_state"] == "no_data"
    assert out["questions"] == []
    assert "上传" in (out.get("hint") or "")


def test_recommend_questions_with_inventory():
    con = writer_conn()
    try:
        con.execute(
            """
            INSERT INTO fact_inventory (inventory_id, stock_qty, location)
            VALUES ('inv1', 10, 'A-01')
            """
        )
    finally:
        con.close()
    out = recommend_questions(model_available=True)
    assert out["data_state"] == "has_data"
    assert "库存总量是多少" in out["questions"]
    assert "超定额物资有多少" in out["questions"]


def test_empty_result_insight_for_metric():
    insight = empty_result_insight(
        question="超定额物资有多少",
        source="metric_template",
        metric_id="INV_OVER_QUOTA_CNT",
    )
    assert insight["empty_reason"]
    assert insight["suggested_next"]
    assert "库存表有多少行" in insight["suggested_next"]


def test_empty_result_insight_for_llm_zero_rows():
    insight = empty_result_insight(
        question="按库位统计电缆库存",
        sql="SELECT location, SUM(stock_qty) FROM fact_inventory WHERE category LIKE '%电缆%' GROUP BY 1",
        source="llm_text2sql",
    )
    assert "筛选" in insight["empty_reason"] or "未命中" in insight["empty_reason"]
    assert insight["suggested_next"]


def test_ask_recommendations_endpoint(client):
    r = client.get("/api/v1/ask/recommendations")
    assert r.status_code == 200
    body = r.json()
    assert "questions" in body
    assert "data_state" in body


def test_ask_zero_stock_metric(client):
    con = writer_conn()
    try:
        con.execute(
            """
            INSERT INTO fact_inventory (inventory_id, stock_qty, location)
            VALUES ('z1', 0, 'A-01'), ('z2', 5, 'A-02')
            """
        )
    finally:
        con.close()
    res = ask("零库存物资有多少")
    assert res["ok"] is True
    assert res["metric_id"] == "INV_ZERO_STOCK_CNT"
    assert res["data"][0]["v"] == 1
