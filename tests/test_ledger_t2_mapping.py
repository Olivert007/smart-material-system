# -*- coding: utf-8 -*-
"""T2: build_domain_rows 将台账扩展列写入 fact 行（ledger_source_samples 抽样）。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

FIXTURE = Path(__file__).parent / "fixtures" / "ledger_source_samples.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_build_domain_rows_inventory_t2_fields():
    from app.services.mapping import build_domain_rows

    fx = _load()
    sheet = next(s for s in fx["sheets"] if s["sheet"] == "备品备件")
    row = sheet["sample_rows"][1]
    df = pd.DataFrame([row], columns=sheet["headers"])
    _, rows = build_domain_rows(
        df,
        domain="inventory",
        file_id="f-test",
        release_id="rel-test",
        source_file=fx["source_file"],
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["belong_system"] == "通信电源系统"
    assert r["project_name"] == "2022年三峡梯调成都区域备品备件补充采购"
    assert r["consumption_plan"] == "损坏更换"
    assert r["material_source"] == "备品备件采购"
    assert r["company_wh_qty"] == 0.0


def test_build_domain_rows_asset_t2_fields():
    from app.services.mapping import build_domain_rows

    fx = _load()
    sheet = next(s for s in fx["sheets"] if s["sheet"] == "公用工器具")
    row = sheet["sample_rows"][0]
    df = pd.DataFrame([row], columns=sheet["headers"])
    _, rows = build_domain_rows(
        df,
        domain="asset",
        file_id="f-test",
        release_id="rel-test",
        source_file=fx["source_file"],
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["asset_qty"] == 1.0
    assert r["tool_source"] == "三峡E购采购"
    assert r["consumption_plan"] == "到期/损坏更换"
    assert r["material_code"] == "E2025005827"


def test_table_field_zh_inventory_location():
    from app.services.field_dict import table_field_zh

    assert table_field_zh("fact_inventory", "location") == "库位"
    assert table_field_zh("fact_asset", "location") == "存放位置"
