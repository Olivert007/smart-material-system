# -*- coding: utf-8 -*-
"""Material align: unique L2 name match remaps flow → inventory id."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_align_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services import material_align as align_svc  # noqa: E402
from app.services.govern.flow_gov import reconcile  # noqa: E402
from app.services.writer import apply_material_align  # noqa: E402


def _seed() -> None:
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM fact_stock_flow")
        con.execute("DELETE FROM fact_inventory")
        con.execute("DELETE FROM dim_material")
        con.execute(
            """
            INSERT INTO dim_material (material_id, material_code, material_name, spec, match_level)
            VALUES
              ('INV_A', 'INV_A', '数字中继板', '', 'L1'),
              ('M-flow-1', '', '数字中继板', '', 'L3'),
              ('M-flow-2', '', '黄底黑字色带', '', 'L3')
            """
        )
        con.execute(
            """
            INSERT INTO fact_inventory (inventory_id, material_id, region, category, stock_qty, opening_qty, source_file)
            VALUES ('i1', 'INV_A', 'r', 'c', 10, 10, 'inv.xlsx')
            """
        )
        con.execute(
            """
            INSERT INTO fact_stock_flow
              (flow_id, material_id, flow_type, quantity, parse_level, parse_source, source_file, source_release_id)
            VALUES
              ('f1', 'M-flow-1', 'OUT', 2, 'L1', 'rule', 'flow.xlsx', 'r1'),
              ('f2', 'M-flow-2', 'OUT', 1, 'L1', 'rule', 'flow.xlsx', 'r1')
            """
        )
    finally:
        con.close()


def main() -> None:
    _seed()
    before = reconcile(persist=False)
    assert before["material_id_overlap"] == 0
    assert before["by_class"]["flow_only"] >= 2

    prop = align_svc.propose_alignment()
    assert prop["unique"] >= 1, prop
    listed = align_svc.list_alignments(status="proposed")
    assert listed["total"] >= 1

    out = align_svc.accept_unique_proposed(actor="test", min_score=0.95, apply_biz=True)
    assert out["accepted"] >= 1, out
    assert out["applied"]["updated_flows"] >= 1, out

    after = reconcile(persist=False)
    assert after["material_id_overlap"] >= 1, after
    # M-flow-1 should be gone from flow_only
    mids = {x["material_id"] for x in after["items"]}
    assert "M-flow-1" not in mids, mids

    # resolve at intake
    mid, hit = align_svc.resolve_material_id(
        code="", name="数字中继板", spec="", file_id="f", row_index=9
    )
    assert mid == "INV_A", (mid, hit)
    print("MATERIAL_ALIGN_OK", {"propose": prop["unique"], "accepted": out["accepted"], "overlap": after["material_id_overlap"]})


if __name__ == "__main__":
    main()
