#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-5 smoke: report run + metric snapshot (REPORT_SNAPSHOT_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_report_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.metrics import ensure_metrics_seed, evaluate_metric, list_metric_snapshots  # noqa: E402
from app.services.report_runner import create_report, run_report  # noqa: E402


def main() -> int:
    init_meta()
    ensure_metrics_seed()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM fact_inventory")
        con.execute(
            """
            INSERT INTO fact_inventory
              (inventory_id, material_id, region, category, source_file, stock_qty, source_release_id)
            VALUES ('i1', 'M1', 'r', 'c', 'f', 9, 'r1')
            """
        )
    finally:
        con.close()

    ev = evaluate_metric("INV_QTY_TOTAL", write_snapshot=True)
    assert ev["value"] == 9, ev
    snaps = list_metric_snapshots("INV_QTY_TOTAL", limit=5)
    assert snaps["total"] >= 1

    create_report(
        name="库存行数",
        query_sql="SELECT material_id, stock_qty FROM fact_inventory",
        actor="smoke",
        report_id="rpt_smoke",
    )
    out = run_report("rpt_smoke", actor="smoke")
    assert out["ok"] and out["row_count"] == 1
    assert Path(out["artifact_path"]).exists()

    print("REPORT_SNAPSHOT_OK")
    print(f"metric_value={ev['value']} report_rows={out['row_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
