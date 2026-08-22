# -*- coding: utf-8 -*-
"""P0-5: reconcile uses stock − opening (docs/12 §6)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_rec_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.govern.flow_gov import reconcile  # noqa: E402


def _seed() -> None:
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM fact_stock_flow")
        con.execute("DELETE FROM fact_inventory")
        # material A: stock=10, opening=3 → expected_net=7; flow_net=7 → no gap
        con.execute(
            """
            INSERT INTO fact_inventory (inventory_id, material_id, region, category, stock_qty, opening_qty, source_file)
            VALUES ('i1', 'A', 'r', 'c', 10, 3, 't.xlsx')
            """
        )
        con.execute(
            """
            INSERT INTO fact_stock_flow
              (flow_id, material_id, flow_type, quantity, parse_level, parse_source, source_file, source_release_id)
            VALUES
              ('f1', 'A', 'IN', 10, 'L1', 'rule', 't.xlsx', 'r1'),
              ('f2', 'A', 'OUT', 3, 'L1', 'rule', 't.xlsx', 'r1')
            """
        )
        # material B: stock=5, opening NULL(=0); flow_net=0 → gap = 0-5 = -5
        con.execute(
            """
            INSERT INTO fact_inventory (inventory_id, material_id, region, category, stock_qty, source_file)
            VALUES ('i2', 'B', 'r', 'c', 5, 't.xlsx')
            """
        )
    finally:
        con.close()


def main() -> None:
    _seed()
    out = reconcile(persist=False)
    assert "opening_qty" in (out.get("formula") or ""), out
    assert out.get("opening_default") == 0
    by_id = {x["material_id"]: x for x in out["items"]}
    assert "A" not in by_id, by_id  # balanced with opening
    assert "B" in by_id, by_id
    assert abs(float(by_id["B"]["gap"]) - (-5.0)) < 1e-6, by_id["B"]
    assert float(by_id["B"]["opening_qty"]) == 0.0
    print("P0_5_OK", {"total": out["total"], "note": out.get("note"), "populated": out.get("opening_populated_rows")})


if __name__ == "__main__":
    main()
