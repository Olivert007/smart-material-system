# -*- coding: utf-8 -*-
"""T8: /api/v1/export/ledger/{sheet} 台账模板导出（LD-5 固定列序 + 台账模板列名）。

实时执行对应 report_definition 种子 SQL，zh=1 表头汉化为台账模板列名（§1.1–§1.4）；
未知 sheet 404；行数/首列与台账模板对齐。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.workers import intake_worker


@pytest.fixture(autouse=True)
def _disable_worker():
    orig = intake_worker.worker.start
    intake_worker.worker.start = lambda: None
    yield
    intake_worker.worker.start = orig


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_export_ledger_template(client):
    from app.repositories import writer_conn

    con = writer_conn()
    try:
        for i in (1, 2):
            con.execute(
                """
                INSERT INTO fact_inventory
                  (inventory_id, material_id, region, category, source_file, source_sheet,
                   stock_qty, opening_qty, unit, location, custodian)
                VALUES (?, ?, '未知', '未分类', 't8.xlsx', '维护材料', ?, ?, '个', 'A1', '张三')
                """,
                [f"INV-T8-{i}", f"M-T8-{i}", 10 + i, i],
            )
        for i in (1, 2):
            con.execute(
                """
                INSERT INTO fact_asset
                  (asset_code, asset_name, company, domain, status, source_file, source_sheet,
                   asset_qty, unit, location, tool_source)
                VALUES (?, ?, '单位', '公具', '在用', 't8.xlsx', '公用工器具', 1, '台', '库房', '购置')
                """,
                [f"AS-T8-{i}", f"工具{i}"],
            )
    finally:
        con.close()

    # 维护材料：台账模板首列「名称」+ 行数（T1.1 BOM 前缀先剥除）
    r = client.get("/api/v1/export/ledger/维护材料")
    assert r.status_code == 200, r.text[:200]
    assert "text/csv" in r.headers.get("content-type", "")
    lines = r.text.splitlines()
    header = lines[0].lstrip("\ufeff")
    assert header.startswith("名称"), lines[0]
    assert "现有库存" in header and "入库数量" in header, lines[0]
    assert len(lines) - 1 == 2

    # 公用工器具：首列「资产编码」+ 台账模板列名（更换周期（年））
    r = client.get("/api/v1/export/ledger/公用工器具")
    assert r.status_code == 200, r.text[:200]
    lines = r.text.splitlines()
    header = lines[0].lstrip("\ufeff")
    assert header.startswith("资产编码"), lines[0]
    assert "更换周期（年）" in header, lines[0]
    assert len(lines) - 1 == 2

    # 未知 sheet → 404
    r = client.get("/api/v1/export/ledger/不存在")
    assert r.status_code == 404


def test_export_ledger_unknown_sheet_404(client):
    assert client.get("/api/v1/export/ledger/weihu").status_code == 404
