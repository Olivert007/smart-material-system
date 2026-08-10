# -*- coding: utf-8 -*-
"""T10.2: 台账 4-sheet 源表头→系统列 对照样例校验（ledger_source_samples.json）。

1. 样例源表头经 resolve_columns 对目标域的关键字段全部命中（源↔系统列映射不漂移）；
2. 样例 sheet 集合与 T8 导出端点 LEDGER_SHEETS 一致（导出模板覆盖全部样例 sheet）；
3. 抽样行关键列有值（样例真实可查）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

FIXTURE = Path(__file__).parent / "fixtures" / "ledger_source_samples.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_ledger_samples_source_headers_resolve():
    from app.services.mapping import resolve_columns

    fx = _load()
    assert fx["source_file"].endswith(".xlsx")
    expect_key = {
        # 维护材料源表无定额列，quota_qty 合法缺失
        "维护材料": ["material_name", "stock_qty", "unit", "location", "opening_qty", "min_qty"],
        "备品备件": [
            "material_name",
            "stock_qty",
            "unit",
            "location",
            "opening_qty",
            "quota_qty",
            "belong_system",
            "project_name",
            "consumption_plan",
            "material_source",
            "company_wh_qty",
        ],
        "应急备汛物资": [
            "material_name",
            "stock_qty",
            "unit",
            "location",
            "quota_qty",
            "group_code",
            "is_frame_material",
            "agreement_supplier",
            "frame_material_code",
            "emergency_supplier",
        ],
        "公用工器具": [
            "asset_code",
            "asset_name",
            "asset_qty",
            "unit",
            "replace_cycle",
            "tool_source",
            "material_code",
            "is_instrument",
            "check_cycle",
            "asset_quota_qty",
        ],
    }
    for s in fx["sheets"]:
        df = pd.DataFrame(columns=s["headers"])
        mapping = resolve_columns(df, s["domain"])
        missing = [f for f in expect_key.get(s["sheet"], []) if not mapping.get(f)]
        assert not missing, (s["sheet"], missing, mapping)


def test_ledger_samples_sheets_match_export_template():
    from app.api.routers.reports import LEDGER_SHEETS

    fx = _load()
    sample_sheets = {s["sheet"] for s in fx["sheets"]}
    assert sample_sheets == set(LEDGER_SHEETS.keys()), (sample_sheets, set(LEDGER_SHEETS.keys()))


def test_ledger_samples_rows_have_values():
    fx = _load()
    key_cols = {
        "inventory": ("物资名称", "名称"),
        "asset": ("物资名称",),
    }
    for s in fx["sheets"]:
        cols = key_cols[s["domain"]]
        assert len(s["sample_rows"]) >= 3, (s["sheet"], len(s["sample_rows"]))
        for row in s["sample_rows"]:
            assert any(row.get(c) for c in cols if c in row), (s["sheet"], row)
