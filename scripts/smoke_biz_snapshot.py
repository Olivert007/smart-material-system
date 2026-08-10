#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2-1 smoke: business snapshot + new metrics (BIZ_SNAPSHOT_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_biz_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.metrics import ensure_metrics_seed, evaluate_metric, list_metrics  # noqa: E402
from app.services.stats_overview import business_snapshot, overview  # noqa: E402


def main() -> int:
    init_meta()
    ensure_metrics_seed()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM fact_inventory")
        con.execute("DELETE FROM fact_demand")
        con.execute("DELETE FROM fact_asset")
        con.execute("DELETE FROM fact_stock_flow")
        con.execute(
            """
            INSERT INTO fact_inventory
              (inventory_id, material_id, region, category, location, source_file,
               stock_qty, quota_qty, stock_value, age_days, source_release_id)
            VALUES
              ('i1', 'M1', 'r', '轴承', 'A1', 'f', 120, 100, 1200, 400, 'r1'),
              ('i2', 'M2', 'r', '轴承', 'A1', 'f', 50, 80, 500, 10, 'r1'),
              ('i3', 'M3', 'r', '阀门', 'B2', 'f', 30, 30, 300, NULL, 'r1')
            """
        )
        con.execute(
            """
            INSERT INTO fact_demand
              (demand_id, material_id, demand_period, quantity, source_file, source_release_id)
            VALUES ('d1', 'M1', '2026Q1', 15, 'f', 'r1')
            """
        )
        con.execute(
            """
            INSERT INTO fact_asset
              (asset_code, asset_name, status, source_file, source_release_id)
            VALUES ('a1', '泵', '在用', 'f', 'r1')
            """
        )
        con.execute(
            """
            INSERT INTO fact_stock_flow
              (flow_id, material_id, flow_type, quantity, parse_level, source_file, source_release_id)
            VALUES
              ('f1', 'M1', 'IN', 10, 'L1', 'f', 'r1'),
              ('f2', 'M1', 'OUT', 3, 'L1', 'f', 'r1')
            """
        )
    finally:
        con.close()

    snap = business_snapshot(top_n=5)
    assert snap["stock_qty_total"] == 200, snap
    assert snap["over_quota_count"] == 1, snap
    assert snap["stale_count"] == 1, snap
    assert snap["demand_qty_total"] == 15, snap
    assert snap["asset_count"] == 1, snap
    assert snap["flow_in_qty"] == 10, snap
    assert snap["flow_out_qty"] == 3, snap
    assert snap["top_by_category"][0]["name"] == "轴承", snap
    assert abs(float(snap["quota_fill_ratio"]) - (200 / 210)) < 1e-6, snap

    for mid in (
        "INV_OVER_QUOTA_CNT",
        "INV_QUOTA_FILL_RATIO",
        "INV_STALE_CNT",
        "FLOW_IN_QTY_TOTAL",
        "FLOW_OUT_QTY_TOTAL",
    ):
        ev = evaluate_metric(mid, write_snapshot=False)
        assert ev.get("active") or ev.get("status") == "active" or ev.get("value") is not None, ev

    ids = {m["metric_id"] for m in list_metrics(status="active")["items"]}
    assert "INV_OVER_QUOTA_CNT" in ids
    ov = overview(recent_limit=3)
    assert ov["business"]["over_quota_count"] == 1

    print("BIZ_SNAPSHOT_OK")
    print(f"stock={snap['stock_qty_total']} over={snap['over_quota_count']} fill={snap['quota_fill_ratio']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
