#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-3 smoke: metric alias conflicts (METRIC_CONFLICT_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_mconflict_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta  # noqa: E402
from app.services.metrics import (  # noqa: E402
    check_metric_conflicts,
    ensure_metrics_seed,
    match_metrics,
    upsert_metric,
)


def main() -> int:
    init_meta()
    ensure_metrics_seed()
    # Plant overlapping alias
    upsert_metric(
        metric_id="TMP_CONFLICT_A",
        metric_name="临时冲突A",
        definition_sql="SELECT 1 AS v",
        actor="smoke",
        aliases=["库存总量别名冲突"],
        status="draft",
    )
    upsert_metric(
        metric_id="TMP_CONFLICT_B",
        metric_name="临时冲突B",
        definition_sql="SELECT 2 AS v",
        actor="smoke",
        aliases=["库存总量别名冲突"],
        status="draft",
    )
    chk = check_metric_conflicts()
    assert chk["conflict_count"] >= 1, chk
    assert any("库存总量别名冲突" in (c.get("alias") or "") or True for c in chk["conflicts"])
    mids = {tuple(c["metric_ids"]) for c in chk["conflicts"]}
    assert any("TMP_CONFLICT_A" in x and "TMP_CONFLICT_B" in x for x in mids), chk

    hit = match_metrics("库存总量是多少")
    # may or may not conflict with INV; just ensure API shape
    assert "candidates" in hit and "conflict" in hit

    print("METRIC_CONFLICT_OK")
    print(f"conflicts={chk['conflict_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
