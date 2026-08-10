# -*- coding: utf-8 -*-
"""PR4: intake plan draft + gate (docs/03 §1.1 / §4.5)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_plan_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["INTAKE_GATE_ENFORCE"] = "1"
os.environ["INTAKE_REQUIRE_PLAN_CONFIRM"] = "1"

sys.path.insert(0, str(ROOT))

from app import config as app_config  # noqa: E402
from app.repositories.db import init_meta, meta_tx  # noqa: E402
from app.services.intake_plan import (  # noqa: E402
    assert_release_gate,
    build_sheet_config,
    confirm_intake_plan,
    gate_preview,
    get_intake_plan,
    save_intake_plan,
)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _plan_gate_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """本模块用例需要 plan-confirm gate 开启；monkeypatch 保证不污染其它模块。"""
    monkeypatch.setattr(app_config, "INTAKE_GATE_ENFORCE", True)
    monkeypatch.setattr(app_config, "INTAKE_REQUIRE_PLAN_CONFIRM", True)



def test_sheet_config_shape():
    cfg = build_sheet_config(
        source="a.xlsx",
        sheet="库存",
        structure="标准纵向",
        adapter="none",
        header_row=2,
        col_map={
            "material_code": "物资编码",
            "material_name": "物资名称",
            "stock_qty": "数量",
            "flow_in_text": "入库记录",
        },
        dedup_std=["material_code"],
        target_domain="inventory",
        role_hint="detail",
    )
    assert cfg["target_table"] == "fact_inventory"
    assert cfg["dedup"] == ["物资编码"]
    assert cfg["master"]["code"] == "物资编码"
    assert any(c["std_field"] == "stock_qty" and c["clean"] == "num_unit" for c in cfg["columns"])
    assert cfg["flow_config"]["flow_columns"][0]["flow_type"] == "IN"


def test_gate_blocks_quality_and_plan_confirm_meta_only():
    init_meta()
    fid = "planfile1"
    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO file_batch (file_id, filename, format, sha256, stored_path, status)
            VALUES (?, 'a.xlsx', 'xlsx', 'h', '/tmp/a.xlsx', 'staged')
            """,
            [fid],
        )

    plan = {
        "step": "intake_plan",
        "file_id": fid,
        "target_domain": "inventory",
        "target_table": "fact_inventory",
        "sheets": [
            build_sheet_config(
                source="a.xlsx",
                sheet="S1",
                structure="标准纵向",
                adapter="none",
                header_row=1,
                col_map={"material_name": "名称", "stock_qty": "数量"},
                dedup_std=["material_name"],
                target_domain="inventory",
            )
        ],
        "mutates_state": False,
    }
    quality = {"blocking": True, "issue_total": 3}
    plan["gate"] = gate_preview(plan=plan, quality=quality, map_pending_count=2)
    assert plan["gate"]["ok"] is False
    assert any(b["code"] == "QUALITY_BLOCKING" for b in plan["gate"]["blockers"])

    save_intake_plan(fid, plan, status="draft")

    try:
        confirm_intake_plan(fid, actor="tester")
        assert False, "should block"
    except RuntimeError as e:
        assert "PLAN_GATE_BLOCKED" in str(e)

    # force confirm plan — still meta only
    res = confirm_intake_plan(fid, actor="tester", force=True, note="ops override")
    assert res["ok"] and res["plan_status"] == "confirmed"
    assert res["mutates_state"] is False
    got = get_intake_plan(fid)
    assert got and got["plan_status"] == "confirmed"

    # release gate: quality still blocking unless force
    try:
        assert_release_gate(fid, force=False)
        assert False, "expected gate blocked"
    except RuntimeError as e:
        assert "GATE_BLOCKED" in str(e)

    assert assert_release_gate(fid, force=True)["forced"] is True


def test_release_requires_plan_confirm_when_gate_ok():
    init_meta()
    fid = "planfile2"
    with meta_tx() as con:
        con.execute(
            """
            INSERT INTO file_batch (file_id, filename, format, sha256, stored_path, status)
            VALUES (?, 'b.xlsx', 'xlsx', 'h2', '/tmp/b.xlsx', 'staged')
            """,
            [fid],
        )
    plan = {
        "step": "intake_plan",
        "file_id": fid,
        "target_domain": "inventory",
        "target_table": "fact_inventory",
        "sheets": [
            build_sheet_config(
                source="b.xlsx",
                sheet="S1",
                structure="标准纵向",
                adapter="none",
                header_row=1,
                col_map={"material_code": "编码", "material_name": "名称", "stock_qty": "数量"},
                dedup_std=["material_code"],
                target_domain="inventory",
            )
        ],
        "mutates_state": False,
    }
    plan["gate"] = gate_preview(plan=plan, quality={"blocking": False, "issue_total": 0})
    assert plan["gate"]["ok"] is True
    save_intake_plan(fid, plan, status="draft")

    try:
        assert_release_gate(fid, force=False)
        assert False, "need plan confirm"
    except RuntimeError as e:
        assert "GATE_PLAN_UNCONFIRMED" in str(e)

    confirm_intake_plan(fid, actor="tester")
    assert assert_release_gate(fid, force=False)["ok"] is True
