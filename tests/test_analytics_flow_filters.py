# -*- coding: utf-8 -*-
"""趋势分析：按物资种类、年份筛选出入库月趋势与 Top 物资。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.query.materials_standardized import STANDARD_CATEGORIES
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
        con.execute(
            "INSERT INTO dim_material (material_id, material_code, material_name, spec, unit, category) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["M-C", "DZ-C", "绝缘胶带", "18mm", "卷", "低值易耗品"],
        )
        rows = [
            ("F1", "M-A", "IN", "2025-01-10", 10, "维护材料"),
            ("F2", "M-A", "OUT", "2025-01-12", 2, "维护材料"),
            ("F3", "M-B", "IN", "2026-08-01", 50, "备品备件"),
            ("F4", "M-C", "IN", "2026-08-02", 5, "低值易耗品"),
            ("F5", "M-A", "IN", "2026-03-01", 8, "维护材料"),
            # source_sheet 为空时仍可按 dim_material.category 命中
            ("F6", "M-A", "IN", "2026-04-01", 3, None),
        ]
        for flow_id, mid, ftype, fdate, qty, sheet in rows:
            con.execute(
                "INSERT INTO fact_stock_flow "
                "(flow_id, material_id, flow_type, flow_date, quantity, unit, source_sheet) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [flow_id, mid, ftype, fdate, qty, "只", sheet],
            )
    finally:
        con.close()


def test_flow_filters_lists_categories_and_years(client):
    _seed()
    r = client.get("/api/v1/analytics/flow-filters")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["categories"] == list(STANDARD_CATEGORIES)
    assert body["years"] == ["2026", "2025"]


def test_flow_monthly_year_slice(client):
    _seed()
    r = client.get("/api/v1/analytics/flow-monthly?year=2025")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["months"] == ["2025-01"]
    assert body["in"] == [10.0]
    assert body["out"] == [2.0]
    assert body["filters"]["year"] == "2025"


def test_flow_monthly_category_and_unknown_ignored(client):
    _seed()
    r = client.get("/api/v1/analytics/flow-monthly?categories=维护材料")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert set(body["months"]) == {"2025-01", "2026-03", "2026-04"}
    by_month = dict(zip(body["months"], zip(body["in"], body["out"])))
    assert by_month["2025-01"] == (10.0, 2.0)
    assert by_month["2026-03"] == (8.0, 0.0)
    assert by_month["2026-04"] == (3.0, 0.0)

    bogus = client.get("/api/v1/analytics/flow-monthly?categories=未知种类")
    assert bogus.status_code == 200
    all_rows = client.get("/api/v1/analytics/flow-monthly")
    assert bogus.json()["months"] == all_rows.json()["months"]
    assert bogus.json()["filters"]["categories"] == []


def test_flow_top_category_year_and_empty_slice(client):
    _seed()
    r = client.get("/api/v1/analytics/flow-top?limit=10&categories=维护材料&year=2025")
    assert r.status_code == 200, r.text[:300]
    items = r.json()["items"]
    assert {it["material_id"] for it in items} == {"M-A"}
    by_type = {it["flow_type"]: it["qty"] for it in items}
    assert by_type["IN"] == 10.0
    assert by_type["OUT"] == 2.0

    empty = client.get("/api/v1/analytics/flow-top?categories=公用工器具")
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    monthly_empty = client.get("/api/v1/analytics/flow-monthly?categories=公用工器具")
    assert monthly_empty.json()["months"] == []
    assert monthly_empty.json()["in"] == []
    assert monthly_empty.json()["out"] == []


def test_flow_year_non_digits_ignored(client):
    _seed()
    r = client.get("/api/v1/analytics/flow-monthly?year=20xx")
    all_rows = client.get("/api/v1/analytics/flow-monthly")
    assert r.json()["months"] == all_rows.json()["months"]
    assert r.json()["filters"]["year"] is None
