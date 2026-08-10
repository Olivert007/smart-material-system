# -*- coding: utf-8 -*-
"""U-5: INV_BELOW_MIN_CNT / INV_EMERGENCY_QUOTA_FILL_RATIO 种子与求值。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_inv_below_min_cnt_evaluate():
    with TestClient(app):
        from app.repositories import writer_conn
        from app.services.metrics.metrics import ensure_business_metrics, evaluate_metric

        ensure_business_metrics(actor="test:u5")
        con = writer_conn()
        try:
            con.execute(
                """
                INSERT INTO fact_inventory
                  (inventory_id, material_id, region, category, source_file, source_sheet,
                   stock_qty, min_qty, unit)
                VALUES
                  ('INV-U5-1', 'M-U5-1', '未知', '未分类', 'u5.xlsx', '维护材料', 1, 3, '个'),
                  ('INV-U5-2', 'M-U5-2', '未知', '未分类', 'u5.xlsx', '维护材料', 5, 2, '个'),
                  ('INV-U5-3', 'M-U5-3', '未知', '未分类', 'u5.xlsx', '维护材料', 4, 4, '个')
                """
            )
            con.execute(
                """
                INSERT INTO fact_inventory
                  (inventory_id, material_id, region, category, source_file, source_sheet,
                   stock_qty, quota_qty, unit)
                VALUES
                  ('INV-U5-E1', 'M-U5-E1', 'TDCD', '未分类', 'u5.xlsx', '应急备汛物资', 1, 2, '台'),
                  ('INV-U5-E2', 'M-U5-E2', 'TDCD', '未分类', 'u5.xlsx', '应急备汛物资', 3, 4, '台')
                """
            )
        finally:
            con.close()

        below = evaluate_metric("INV_BELOW_MIN_CNT", write_snapshot=False)
        assert below["value"] == 1
        assert below["data_status"] == "ok"

        emergency = evaluate_metric("INV_EMERGENCY_QUOTA_FILL_RATIO", write_snapshot=False)
        assert emergency["data_status"] == "ok"
        assert abs(emergency["value"] - (4 / 6)) < 1e-6
