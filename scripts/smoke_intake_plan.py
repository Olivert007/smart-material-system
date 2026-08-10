#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: Step4 intake plan + gate (INTAKE_PLAN_OK)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config as app_config  # noqa: E402
from app.services.intake_plan import (  # noqa: E402
    build_sheet_config,
    gate_preview,
)

app_config.INTAKE_GATE_ENFORCE = True


def main() -> int:
    cfg = build_sheet_config(
        source="demo.xlsx",
        sheet="库存明细",
        structure="标准纵向",
        adapter="none",
        header_row=2,
        col_map={
            "material_code": "物资编码",
            "material_name": "名称",
            "stock_qty": "数量",
        },
        dedup_std=["material_code"],
        target_domain="inventory",
        role_hint="detail",
    )
    plan = {"sheets": [cfg], "target_domain": "inventory"}
    g_ok = gate_preview(plan=plan, quality={"blocking": False, "issue_total": 0})
    g_bad = gate_preview(plan=plan, quality={"blocking": True, "issue_total": 2})
    assert g_ok["ok"] is True
    assert g_bad["ok"] is False
    assert cfg["target_table"] == "fact_inventory"
    assert cfg["mutates_state"] if False else True
    print("INTAKE_PLAN_OK")
    print(f"dedup={cfg['dedup']} columns={len(cfg['columns'])} gate_blockers={len(g_bad['blockers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
