# -*- coding: utf-8 -*-
"""数据成果页·趋势分析新增板块：流水概览 KPI / 库存健康 / 资产清查 / 需求 / 定额调整。"""
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
            "INSERT INTO dim_material (material_id, material_code, material_name, spec, unit, category) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["M-A", "WH-A", "电力电缆", "YJV", "米", "维护材料"],
        )
        con.execute(
            "INSERT INTO dim_material (material_id, material_code, material_name, spec, unit, category) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["M-B", "BP-B", "备件开关", "10kV", "只", "备品备件"],
        )
        for flow_id, mid, ftype, fdate, qty in [
            ("F1", "M-A", "IN", "2025-01-10", 10),
            ("F2", "M-A", "OUT", "2025-01-12", 2),
            ("F3", "M-B", "IN", "2026-08-01", 50),
        ]:
            con.execute(
                "INSERT INTO fact_stock_flow "
                "(flow_id, material_id, flow_type, flow_date, quantity, unit) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [flow_id, mid, ftype, fdate, qty, "只"],
            )
        # 库存：含低库存与超定额样本（I1 低库存但不超过定额，I2 超定额但不低于最低库存）
        con.execute(
            "INSERT INTO fact_inventory "
            "(inventory_id, material_id, category, region, stock_qty, min_qty, quota_qty) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["I1", "M-A", "维护材料", "成都", 5, 10, 8],
        )
        con.execute(
            "INSERT INTO fact_inventory "
            "(inventory_id, material_id, category, region, stock_qty, min_qty, quota_qty) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["I2", "M-B", "备品备件", "成都", 100, 5, 20],
        )
        # 资产
        con.execute(
            "INSERT INTO fact_asset "
            "(asset_code, asset_name, company, domain, status, purchase_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["A1", "服务器", "CTGCY", "TDCD", "正常", "2020-05-01"],
        )
        con.execute(
            "INSERT INTO fact_asset "
            "(asset_code, asset_name, company, domain, status, purchase_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["A2", "交换机", "CYPC", "TD", "正常", "2022-03-01"],
        )
        # 需求
        con.execute(
            "INSERT INTO fact_demand (demand_id, material_id, demand_period, quantity) "
            "VALUES (?, ?, ?, ?)",
            ["D1", "M-A", "2026.1", 30],
        )
        # 定额调整
        con.execute(
            "INSERT INTO fact_quota_adjust (quota_id, material_id, adjust_type, verified_quota) "
            "VALUES (?, ?, ?, ?)",
            ["Q1", "M-B", "核定", 50],
        )
    finally:
        con.close()


def test_flow_summary_kpis(client):
    _seed()
    r = client.get("/api/v1/analytics/flow-summary")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["total"] == 3
    assert body["in"]["qty"] == 60.0
    assert body["out"]["qty"] == 2.0
    assert body["net"] == 58.0
    assert body["materials"] == 2
    assert body["min_date"] == "2025-01-10"
    assert body["max_date"] == "2026-08-01"

    y = client.get("/api/v1/analytics/flow-summary?year=2025")
    assert y.json()["total"] == 2
    assert y.json()["filters"]["year"] == "2025"


def test_inventory_health(client):
    _seed()
    r = client.get("/api/v1/analytics/inventory-health?top_n=5")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["total"] == 2
    cats = {c["name"]: c for c in body["by_category"]}
    assert cats["维护材料"]["count"] == 1
    assert body["by_region"][0]["name"] == "成都"
    # I1: stock 5 < min 10 → 低库存；I2: stock 100 > quota 20 → 超定额
    assert body["low_stock"]["count"] == 1
    assert body["low_stock"]["items"][0]["stock_qty"] == 5.0
    assert body["over_quota"]["count"] == 1
    assert body["over_quota"]["items"][0]["stock_qty"] == 100.0


def test_asset_overview(client):
    _seed()
    r = client.get("/api/v1/analytics/asset-overview")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["total"] == 2
    assert body["company_count"] == 2
    assert body["domain_count"] == 2
    by_company = {c["name"]: c["count"] for c in body["by_company"]}
    assert by_company["CTGCY"] == 1
    assert by_company["CYPC"] == 1
    years = {c["name"]: c["count"] for c in body["by_year"]}
    assert years.get("2020") == 1
    assert years.get("2022") == 1


def test_demand_and_quota_overview(client):
    _seed()
    d = client.get("/api/v1/analytics/demand-overview")
    assert d.status_code == 200, d.text[:300]
    assert d.json()["total"] == 1
    assert d.json()["quantity"] == 30.0
    assert d.json()["materials"] == 1
    assert d.json()["top"][0]["qty"] == 30.0

    q = client.get("/api/v1/analytics/quota-overview")
    assert q.status_code == 200, q.text[:300]
    assert q.json()["total"] == 1
    assert q.json()["by_type"][0]["name"] == "核定"
    assert q.json()["top"][0]["verified_qty"] == 50.0
