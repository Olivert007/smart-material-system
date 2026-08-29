# -*- coding: utf-8 -*-
"""Step5: ask engine compare harness (docs/19)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_ask_cmp_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["VANNA_PERSIST_DIR"] = str(TMP / "vanna")
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["LLM_BIG_ENDPOINT"] = ""
os.environ["LLM_FAST_ENDPOINT"] = ""

sys.path.insert(0, str(ROOT))

from app.services.query.ask_engine_eval import (  # noqa: E402
    ASK_COMPARE_CASES,
    run_compare,
    score_sql_must_contain,
    summarize_engine_runs,
)


def test_compare_cases_count_is_20():
    assert len(ASK_COMPARE_CASES) == 20
    ids = [c["id"] for c in ASK_COMPARE_CASES]
    assert len(set(ids)) == 20


def test_score_sql_must_contain():
    sc = score_sql_must_contain(
        "SELECT location, COUNT(*) FROM fact_inventory GROUP BY location LIMIT 10",
        ["fact_inventory", "location", "group"],
    )
    assert sc["contain_ok"] is True
    sc2 = score_sql_must_contain("SELECT 1", ["fact_inventory"])
    assert sc2["contain_ok"] is False


def test_summarize_engine_runs():
    details = [
        {
            "ok": True,
            "exec_ok": True,
            "contain_ok": True,
            "source": "metric_template",
            "latency_ms": 1,
        },
        {
            "ok": False,
            "exec_ok": False,
            "contain_ok": False,
            "source": "llm_text2sql",
            "engine_fallback": True,
            "latency_ms": 2,
        },
    ]
    s = summarize_engine_runs(details)
    assert s["n"] == 2
    assert s["ok"] == 1
    assert s["metric_template_hits"] == 1
    assert s["engine_fallback_count"] == 1


def test_run_compare_offline_writes_json():
    out_path = TMP / "ask_engine_compare.json"
    payload = run_compare(offline=True, out_path=out_path)
    assert payload["ok"] is True
    assert payload["offline"] is True
    assert payload["n_cases"] == 20
    assert "legacy" in payload["summary"]
    assert "vanna" in payload["summary"]
    assert out_path.is_file()
    raw = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(raw["cases"]) == 20
    metric_rows = [c for c in raw["cases"] if c["kind"] in ("metric", "metric_or_simple")]
    assert metric_rows
    assert all(c["engines"]["legacy"]["ok"] for c in metric_rows)
