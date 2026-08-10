# -*- coding: utf-8 -*-
"""Opening seed for inv_only materials (docs/12 §6)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_open_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.flow_gov import reconcile  # noqa: E402
from app.services.writer import seed_opening_from_snapshot  # noqa: E402


def _seed() -> None:
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM fact_stock_flow")
        con.execute("DELETE FROM fact_inventory")
        # inv-only with stock → should get opening=stock after seed
        con.execute(
            """
            INSERT INTO fact_inventory (inventory_id, material_id, region, category, stock_qty, source_file)
            VALUES ('i1', 'INV1', 'r', 'c', 12, 'inv.xlsx')
            """
        )
        # flow-only → seed must not invent inventory
        con.execute(
            """
            INSERT INTO fact_stock_flow
              (flow_id, material_id, flow_type, quantity, parse_level, parse_source, source_file, source_release_id)
            VALUES ('f1', 'FLOW1', 'IN', 5, 'L1', 'rule', 'flow.xlsx', 'r1')
            """
        )
        # both present mismatch → seed must NOT overwrite opening
        con.execute(
            """
            INSERT INTO fact_inventory (inventory_id, material_id, region, category, stock_qty, opening_qty, source_file)
            VALUES ('i2', 'BOTH1', 'r', 'c', 10, 0, 'inv.xlsx')
            """
        )
        con.execute(
            """
            INSERT INTO fact_stock_flow
              (flow_id, material_id, flow_type, quantity, parse_level, parse_source, source_file, source_release_id)
            VALUES ('f2', 'BOTH1', 'IN', 3, 'L1', 'rule', 'flow.xlsx', 'r1')
            """
        )
    finally:
        con.close()


def main() -> None:
    _seed()
    before = reconcile(persist=False)
    by = {x["material_id"]: x for x in before["items"]}
    assert "INV1" in by and by["INV1"]["gap_class"] == "inv_only", by
    assert "FLOW1" in by and by["FLOW1"]["gap_class"] == "flow_only", by
    assert "BOTH1" in by and by["BOTH1"]["gap_class"] == "mismatch", by
    assert before["by_class"]["inv_only"] >= 1
    assert before["material_id_overlap"] == 1

    dry = seed_opening_from_snapshot(actor="test", dry_run=True)
    assert dry["would_update"] == 1, dry

    out = seed_opening_from_snapshot(actor="test", dry_run=False)
    assert out["updated"] == 1, out

    after = reconcile(persist=False)
    by2 = {x["material_id"]: x for x in after["items"]}
    assert "INV1" not in by2, by2  # balanced after opening=stock
    assert "FLOW1" in by2 and by2["FLOW1"]["gap_class"] == "flow_only"
    assert "BOTH1" in by2 and by2["BOTH1"]["gap_class"] == "mismatch"
    assert after["by_class"]["inv_only"] == 0
    assert after["opening_populated_rows"] >= 1
    print("OPENING_SEED_OK", {"before": before["total"], "after": after["total"], "by_class": after["by_class"]})


if __name__ == "__main__":
    main()
