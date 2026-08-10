# -*- coding: utf-8 -*-
"""PR5: metric template-first ask + business metric seed + sql_fewshot."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_metric_ask_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["LLM_BIG_ENDPOINT"] = ""
os.environ["LLM_FAST_ENDPOINT"] = ""

sys.path.insert(0, str(ROOT))

from app.repositories import meta_conn, writer_conn  # noqa: E402
from app.repositories.db import init_meta  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.fewshot import ensure_sql_fewshot_seed  # noqa: E402
from app.services.metrics import ensure_metrics_seed, match_metrics  # noqa: E402
from app.services.text2sql import ask  # noqa: E402


def test_business_metrics_seeded_and_match():
    init_meta()
    ensure_metrics_seed()
    m = match_metrics("库存总数量是多少")
    assert m["best"] and m["best"]["metric_id"] == "INV_QTY_TOTAL"
    assert m["conflict"] is False

    m2 = match_metrics("需求总量是多少")
    assert m2["best"]["metric_id"] == "DEMAND_QTY_TOTAL"


def test_ask_uses_metric_template_without_llm():
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()
    ensure_metrics_seed()
    res = ask("库存总数量是多少")
    assert res["ok"] is True
    assert res["source"] == "metric_template"
    assert res["model_invoked"] is False
    assert res["metric_id"] == "INV_QTY_TOTAL"
    assert res["sql"] and "fact_inventory" in res["sql"]
    assert "data" in res


def test_flow_draft_blocked_in_ask():
    init_meta()
    ensure_metrics_seed()
    # U-4：质量门指标展示名/别名收紧后，质量门口径问题仍被门禁拦截
    res = ask("勾稽差异行数是多少")
    assert res["ok"] is False
    assert res.get("code") == "FLOW_QUALITY_GATE"
    assert res["model_invoked"] is False
    # U-4：原「出入库总量」别名已移除，不再命中质量门指标 FLOW_QTY_TOTAL
    m = match_metrics("出入库总量是多少")
    assert not (m["best"] and m["best"]["metric_id"] == "FLOW_QTY_TOTAL")


def test_sql_fewshot_table_seeded():
    init_meta()
    out = ensure_sql_fewshot_seed()
    assert out["ok"]
    con = meta_conn()
    try:
        n = con.execute("SELECT COUNT(*) AS c FROM sql_fewshot").fetchone()["c"]
    finally:
        con.close()
    assert n >= 3
