# -*- coding: utf-8 -*-
"""PR6: master_pending → writer.master_apply (docs/04 §7)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_master_gov_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.master_gov import confirm_pending, list_pending, propose_from_dim  # noqa: E402


def _seed() -> None:
    init_meta()
    with meta_tx() as con:
        con.execute("DELETE FROM master_pending")
        con.execute("DELETE FROM write_audit WHERE action='master_apply'")
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM fact_stock_flow")
        con.execute("DELETE FROM dim_material")
        con.execute(
            """
            INSERT INTO dim_material
              (material_id, material_code, material_name, spec, unit, match_level, code_source)
            VALUES
              ('L1_OK', 'C001', '已确认物料', 'A', '个', 'L1', 'seed'),
              ('L3_NEW', 'C900', '新发现物料', 'B', '箱', 'L3', ''),
              ('L3_DUP', 'C001', '同码异物名', 'C', '个', 'L3', ''),
              ('L3_SAME', 'C901', '新发现物料', 'B', '箱', 'L3', '')
            """
        )
        con.execute(
            """
            INSERT INTO fact_stock_flow
              (flow_id, material_id, flow_type, quantity, parse_level, parse_source, source_file, source_release_id)
            VALUES ('f1', 'L3_SAME', 'OUT', 1, 'L1', 'rule', 'f.xlsx', 'r1')
            """
        )
    finally:
        con.close()


def test_propose_enqueues_l3_with_conflict() -> None:
    _seed()
    out = propose_from_dim()
    assert out["enqueued"] >= 3, out
    listed = list_pending(status="pending")
    assert listed["total"] >= 3
    by_id = {i["material_id"]: i for i in listed["items"]}
    assert "L3_NEW" in by_id
    assert "L1_OK" not in by_id
    # code_same_name_diff: C001 shared by L1_OK and L3_DUP
    assert by_id["L3_DUP"].get("conflict_type") == "code_same_name_diff"
    # name_same_code_diff: L3_NEW vs L3_SAME
    assert by_id["L3_SAME"].get("conflict_type") in (
        "name_same_code_diff",
        "code_same_name_diff",
        "spec_diff",
    ) or by_id["L3_NEW"].get("conflict_type") == "name_same_code_diff"


def test_approve_writes_dim_and_audit() -> None:
    _seed()
    propose_from_dim()
    listed = list_pending(status="pending")
    pid = next(i["pending_id"] for i in listed["items"] if i["material_id"] == "L3_NEW")
    res = confirm_pending(pending_id=pid, decision="approve", actor="tester")
    assert res["ok"] and res["status"] == "approved" and res["mutates_biz"]

    con = writer_conn()
    try:
        row = con.execute(
            "SELECT match_level, code_source FROM dim_material WHERE material_id='L3_NEW'"
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == "approved" and row[1] == "master_confirm"

    with meta_tx() as mcon:
        audits = mcon.execute(
            "SELECT COUNT(*) AS c FROM write_audit WHERE action='master_apply'"
        ).fetchone()["c"]
    assert audits >= 1

    # re-propose should not re-enqueue approved
    out2 = propose_from_dim()
    listed2 = list_pending(status="pending")
    assert all(i["material_id"] != "L3_NEW" for i in listed2["items"])
    assert out2["enqueued"] == 0 or "L3_NEW" not in {
        i["material_id"] for i in list_pending()["items"]
    }


def test_merge_remaps_flows() -> None:
    _seed()
    propose_from_dim()
    listed = list_pending(status="pending")
    pid = next(i["pending_id"] for i in listed["items"] if i["material_id"] == "L3_SAME")
    res = confirm_pending(
        pending_id=pid,
        decision="merge",
        actor="tester",
        merge_to_material_id="L3_NEW",
    )
    assert res["ok"] and res["status"] == "merged"
    con = writer_conn()
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM fact_stock_flow WHERE material_id='L3_NEW'"
        ).fetchone()[0]
        left = con.execute(
            "SELECT COUNT(*) FROM fact_stock_flow WHERE material_id='L3_SAME'"
        ).fetchone()[0]
        ml = con.execute(
            "SELECT match_level, code_source FROM dim_material WHERE material_id='L3_SAME'"
        ).fetchone()
    finally:
        con.close()
    assert n >= 1 and left == 0
    assert ml[0] == "merged" and ml[1] == "master_merge"


def test_reject_marks_dim() -> None:
    _seed()
    propose_from_dim()
    listed = list_pending(status="pending")
    pid = next(i["pending_id"] for i in listed["items"] if i["material_id"] == "L3_DUP")
    res = confirm_pending(pending_id=pid, decision="reject", actor="tester", note="同码异物")
    assert res["ok"] and res["status"] == "rejected"
    con = writer_conn()
    try:
        row = con.execute(
            "SELECT match_level, code_source FROM dim_material WHERE material_id='L3_DUP'"
        ).fetchone()
    finally:
        con.close()
    assert row[0] == "L3_rejected" and row[1] == "master_reject"


def test_approve_applies_material_patch() -> None:
    _seed()
    propose_from_dim()
    listed = list_pending(status="pending")
    pid = next(i["pending_id"] for i in listed["items"] if i["material_id"] == "L3_NEW")
    res = confirm_pending(
        pending_id=pid,
        decision="approve",
        actor="tester",
        material_patch={"material_code": "C900-FIX", "material_name": "修正后物料"},
    )
    assert res["ok"] and res["status"] == "approved"
    con = writer_conn()
    try:
        row = con.execute(
            "SELECT material_code, material_name FROM dim_material WHERE material_id='L3_NEW'"
        ).fetchone()
    finally:
        con.close()
    assert row[0] == "C900-FIX" and row[1] == "修正后物料"


def main() -> None:
    test_propose_enqueues_l3_with_conflict()
    print("OK propose")
    test_approve_writes_dim_and_audit()
    print("OK approve")
    test_merge_remaps_flows()
    print("OK merge")
    test_reject_marks_dim()
    print("OK reject")
    print("MASTER_GOV_OK")


if __name__ == "__main__":
    main()
