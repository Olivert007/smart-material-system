# -*- coding: utf-8 -*-
"""数据成果页评审 §2.3/§8.4: /api/v1/analytics/flow-top 统计口径。

修复前：按 (material_id, flow_type) 单行 qty 排序 + LIMIT，IN/OUT 对比可能被截断
（例如 Top10 全为 IN，OUT 缺失）。
修复后：先按物资总出入库量（SUM(quantity)）选 TopN 物资，再返回这些物资的
IN/OUT 分组行；同时校验 asset_code 优先取 dim_material.material_code、
为空时回退 material_id，display_name 保留中文展示。
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
        # M-1 无 material_code → asset_code 回退 material_id；M-2 有 material_code。
        con.execute(
            "INSERT INTO dim_material (material_id, material_code, material_name, spec, unit, category) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["M-1", None, "光缆", "G1-24", "卷", "缆材"],
        )
        con.execute(
            "INSERT INTO dim_material (material_id, material_code, material_name, spec, unit, category) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["M-2", "MC-002", "光衰", "FC", "只", "器件"],
        )
        con.execute(
            "INSERT INTO dim_material (material_id, material_code, material_name, spec, unit, category) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["M-3", None, "接头盒", "J-1", "个", "辅材"],
        )
        # 总出入库量：M-2=110 最高，M-1=102 次之，M-3=30。
        rows = [
            ("F1", "M-1", "IN", "2026-08-01", 100),
            ("F2", "M-1", "OUT", "2026-08-02", 2),
            ("F3", "M-2", "IN", "2026-08-01", 60),
            ("F4", "M-2", "OUT", "2026-08-03", 50),
            ("F5", "M-3", "IN", "2026-08-04", 30),
        ]
        for flow_id, mid, ftype, fdate, qty in rows:
            con.execute(
                "INSERT INTO fact_stock_flow (flow_id, material_id, flow_type, flow_date, quantity, unit) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [flow_id, mid, ftype, fdate, qty, "只"],
            )
    finally:
        con.close()


def test_flow_top_keeps_in_out_pair_for_top_materials(client):
    """Top 物资的 IN/OUT 行必须成对返回，不因单行 LIMIT 截断 OUT。"""
    _seed()
    r = client.get("/api/v1/analytics/flow-top?limit=2")
    assert r.status_code == 200, r.text[:300]
    items = r.json()["items"]
    assert len(items) == 4, items  # M-1 IN/OUT + M-2 IN/OUT
    by_key = {}
    for it in items:
        by_key.setdefault(it["material_id"], []).append(it["flow_type"])
    # Top2 物资 = M-2(110)、M-1(102)，M-3(30) 不应出现
    assert set(by_key) == {"M-1", "M-2"}
    # 每个 Top 物资 IN/OUT 齐全（旧实现此处 OUT 会被截断）
    assert sorted(by_key["M-1"]) == ["IN", "OUT"]
    assert sorted(by_key["M-2"]) == ["IN", "OUT"]


def test_flow_top_asset_code_fallback_and_zh(client):
    _seed()
    r = client.get("/api/v1/analytics/flow-top?limit=2")
    items = r.json()["items"]
    m1 = next(it for it in items if it["material_id"] == "M-1")
    m2 = next(it for it in items if it["material_id"] == "M-2")
    # 无 material_code 时回退 material_id；有时取 material_code
    assert m1["asset_code"] == "M-1"
    assert m2["asset_code"] == "MC-002"
    # display_name 保留中文物资展示
    assert "光缆" in m1["display_name"]
    assert "光衰" in m2["display_name"]
