# -*- coding: utf-8 -*-
"""Step3: Vanna training from local trusted sources."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_vanna_train_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["VANNA_PERSIST_DIR"] = str(TMP / "vanna")
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.repositories import writer_conn  # noqa: E402
from app.repositories.db import init_meta  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.fewshot import ensure_sql_fewshot_seed  # noqa: E402
from app.services.metrics import ensure_metrics_seed  # noqa: E402
from app.services.query.vanna_local import store_stats  # noqa: E402
from app.services.query.vanna_train import collect_training_payload, train_vanna_ask  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()
    ensure_metrics_seed()
    ensure_sql_fewshot_seed()


def test_collect_training_payload_has_sources():
    payload = collect_training_payload()
    assert payload["documentation"]
    assert len(payload["ddl"]) >= 3
    qs = payload["question_sql"]
    assert len(qs) >= 10
    sources = {row["source"] for row in qs}
    assert any(str(s).startswith("domain_sample") for s in sources)
    assert any(str(s).startswith("metric") for s in sources)
    # fewshot 与 domain/指标样例可能因去重而不单独出现在 source 中


def test_train_vanna_ask_writes_store_and_manifest():
    out = train_vanna_ask(replace=True)
    assert out["ok"] is True
    assert out["question_sql_count"] >= 10
    assert out["ddl_count"] >= 3
    assert out["documentation_count"] >= 1

    store_path = Path(config.VANNA_PERSIST_DIR) / "store.json"
    manifest_path = Path(config.VANNA_PERSIST_DIR) / "manifest.json"
    assert store_path.is_file()
    assert manifest_path.is_file()

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(raw.get("question_sql") or []) == out["question_sql_count"]
    stats = store_stats()
    assert stats["question_sql_count"] == out["question_sql_count"]
