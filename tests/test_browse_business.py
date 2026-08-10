# -*- coding: utf-8 -*-
"""DT-W1: /api/v1/browse/{table}?mode=business 业务明细视图（question/14 §3.1）。

- 默认 business：事实表走 v_browse_* 视图（JOIN dim_material），名称/规格/单位前置、
  material_id 置后列供溯源；flow_type 值域汉化；
- mode=raw：物理表直出（不拼名称）；
- 未知表 404；非法 mode 400。
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


def _seed():
    from app.repositories import writer_conn

    con = writer_conn()
    try:
        con.execute(
            "INSERT INTO dim_material (material_id, material_name, spec, unit, category) VALUES (?, ?, ?, ?, ?)",
            ["M-1", "电力电缆", "YJV-0.6/1kV", "米", "电缆"],
        )
        for i in (1, 2):
            con.execute(
                """
                INSERT INTO fact_inventory
                  (inventory_id, material_id, region, category, source_file, source_sheet,
                   stock_qty, opening_qty, unit, location, custodian, remark, belong_system)
                VALUES (?, ?, '川云', '电缆', 'browse.xlsx', '维护材料', ?, ?, '米', 'A1', '张三', '备注', '系统X')
                """,
                [f"INV-B-{i}", "M-1", 10 + i, i],
            )
        con.execute(
            """
            INSERT INTO fact_stock_flow
              (flow_id, material_id, flow_type, flow_date, quantity, unit, person, purpose)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ["FL-B-1", "M-1", "IN", "2026-08-01", 5, "米", "李四", "检修领用"],
        )
    finally:
        con.close()


def test_browse_business_joins_material(client):
    _seed()
    r = client.get("/api/v1/browse/fact_inventory?mode=business")
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["mode"] == "business"
    cols = data["columns_zh"]
    assert "物资名称" in cols, cols
    assert "规格型号" in cols
    # 名称/规格/单位 置于 物资ID 之前（doc: 名称置于 ID 前，ID 放后列供溯源）
    assert cols.index("物资名称") < cols.index("物资ID"), cols
    assert cols.index("单位") < cols.index("物资ID"), cols
    row = data["rows"][0]
    assert row["物资名称"] == "电力电缆"
    assert row["规格型号"] == "YJV-0.6/1kV"
    assert data["total"] == 2


def test_browse_default_mode_is_business(client):
    _seed()
    r = client.get("/api/v1/browse/fact_stock_flow")
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["mode"] == "business"
    cols = data["columns_zh"]
    assert "物资名称" in cols
    assert "出入类型" in cols
    # flow_type 值域汉化（IN→入库）
    assert data["rows"][0]["出入类型"] == "入库"


def test_browse_raw_no_join(client):
    _seed()
    r = client.get("/api/v1/browse/fact_inventory?mode=raw")
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["mode"] == "raw"
    cols = data["columns_zh"]
    assert "物资名称" not in cols, cols  # raw 物理表直出，不拼名称
    assert "物资ID" in cols


def test_browse_bad_mode_400(client):
    _seed()
    r = client.get("/api/v1/browse/fact_inventory?mode=hack")
    assert r.status_code == 400


def test_browse_unknown_table_404(client):
    assert client.get("/api/v1/browse/no_such_table").status_code == 404
