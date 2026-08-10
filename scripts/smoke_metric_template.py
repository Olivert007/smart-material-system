#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: metric template ask (METRIC_TEMPLATE_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_metric_smoke_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)

sys.path.insert(0, str(ROOT))

from app.repositories import init_meta, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.fewshot import ensure_sql_fewshot_seed  # noqa: E402
from app.services.metrics import ensure_metrics_seed, match_metrics  # noqa: E402
from app.services.text2sql import ask  # noqa: E402


def main() -> int:
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()
    ensure_metrics_seed()
    ensure_sql_fewshot_seed()
    m = match_metrics("库存总数量是多少")
    assert m["best"]["metric_id"] == "INV_QTY_TOTAL"
    res = ask("库存总数量是多少")
    assert res["ok"] and res["source"] == "metric_template"
    blocked = ask("勾稽差异行数是多少")
    assert blocked.get("code") == "FLOW_QUALITY_GATE", blocked
    print("METRIC_TEMPLATE_OK")
    print(f"inv={res['answer']} flow_blocked={blocked.get('code')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
