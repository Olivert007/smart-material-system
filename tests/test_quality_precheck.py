# -*- coding: utf-8 -*-
"""PR3: Step3 rule quality precheck (docs/03)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.intake.quality_precheck import run_quality_precheck  # noqa: E402


def test_clean_inventory_ok():
    df = pd.DataFrame(
        {
            "物资编码": ["A1", "A2"],
            "物资名称": ["电缆", "螺栓"],
            "数量": ["10", "20"],
        }
    )
    col_map = {"material_code": "物资编码", "material_name": "物资名称", "stock_qty": "数量"}
    q = run_quality_precheck(df, domain="inventory", col_map=col_map)
    assert q["ok"] is True
    assert q["blocking"] is False
    assert q["issue_total"] == 0
    assert q["suggested_dedup"] == ["material_code"]


def test_missing_required_and_dup_and_qty():
    df = pd.DataFrame(
        {
            "物资编码": ["A1", "A1", "", "A3"],
            "物资名称": ["电缆", "电缆2", "无名", "垫片"],
            "数量": ["10", "20", "abc", "2023"],
        }
    )
    col_map = {"material_code": "物资编码", "material_name": "物资名称", "stock_qty": "数量"}
    q = run_quality_precheck(df, domain="inventory", col_map=col_map)
    assert q["ok"] is False
    counts = q["issue_counts"]
    assert counts["duplicate_pk"] >= 2
    assert counts["qty_non_numeric"] >= 1
    assert counts["qty_year_like"] >= 1
    # year-like / non-numeric 是疑似值告警，不再阻塞发布（真实数量如 2000/2023 合法）
    assert q["blocking"] is False
    codes = {i["code"] for i in q["issues_sample"]}
    assert "DUPLICATE_PK" in codes
    assert "QTY_YEAR_LIKE" in codes or "QTY_NON_NUMERIC" in codes
    blob = str(q.get("hint") or "") + " " + " ".join(str(i.get("detail") or "") for i in q["issues_sample"])
    assert "blocking=true" not in blob
    assert "required group blank" not in blob
    assert "LLM" not in blob
    assert "key=" not in blob
    assert any("异常" in str(i.get("detail") or "") for i in q["issues_sample"])


def test_required_unmapped_blocking():
    df = pd.DataFrame({"备注": ["x", "y"]})
    col_map = {"remark": "备注"}
    q = run_quality_precheck(df, domain="inventory", col_map=col_map)
    assert q["blocking"] is True
    assert q["issue_counts"]["missing_required"] >= 2
    assert any(i["code"] == "REQUIRED_UNMAPPED" for i in q["issues_sample"])


def test_negative_qty():
    df = pd.DataFrame(
        {
            "名称": ["a"],
            "数量": ["-5"],
        }
    )
    col_map = {"material_name": "名称", "stock_qty": "数量"}
    q = run_quality_precheck(df, domain="inventory", col_map=col_map)
    assert q["issue_counts"]["qty_negative"] == 1
