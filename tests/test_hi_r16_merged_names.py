# -*- coding: utf-8 -*-
"""HI-R16: 维护材料合并单元格中的名称不得被当成空值拦截。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from app.services.govern import flow_config as fc
from app.services.intake.evidence import load_stock_flow_tabular
from app.services.mapping import resolve_columns
from app.services.value_validator import apply_checks


@pytest.fixture(autouse=True)
def _reload_route():
    fc._reload_ledger_route()
    yield
    fc._reload_ledger_route()


def _write_weihu_merged(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "维护材料"
    ws.append(["通信部成都区域维护材料物资库存表"])
    ws.append(["注意：表中含公式"])
    ws.append(
        [
            "序号",
            "名称",
            "品牌型号规格",
            "现有库存",
            "单位",
            "存放位置",
            "入库记录",
            "入库数量",
            "出库记录",
            "出库数量",
        ]
    )
    ws.append(["例", "插线板", "示例规格", "1", "个", "仓库", "", "", "", ""])
    ws.append(["", "", "", "", "", "", "", "", "", ""])
    ws.append(["1", "南孚电池", "7号", "8", "个", "向家坝14号楼215", "", "", "", ""])
    ws.append(["2", None, "5号", "4", "盒", "向家坝14号楼215", "", "", "", ""])
    ws.append(["3", None, "7号", "4", "盒", "向家坝14号楼215", "", "", "", ""])
    ws.merge_cells("B6:B8")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def test_merged_material_name_survives_stock_flow_load(tmp_path: Path):
    fc._reload_ledger_route()
    xlsx = _write_weihu_merged(tmp_path / "weihu.xlsx")
    df = load_stock_flow_tabular(xlsx)
    weihu = df[df["sheet"].astype(str) == "维护材料"].copy()
    weihu = weihu[weihu["material_name"].astype(str).str.strip() != "插线板"]
    names = weihu["material_name"].astype(str).str.strip().tolist()
    assert names.count("南孚电池") >= 3, names
    specs = [str(s) for s in weihu["spec"].tolist()]
    assert any("5号" in s for s in specs)
    assert any("7号" in s for s in specs)


def test_merged_material_name_not_blocked_by_required_rule(tmp_path: Path):
    from app.repositories.db import init_meta

    init_meta()
    fc._reload_ledger_route()
    xlsx = _write_weihu_merged(tmp_path / "weihu.xlsx")
    df = load_stock_flow_tabular(xlsx)
    weihu = df[df["sheet"].astype(str) == "维护材料"].reset_index(drop=True)
    col_map = resolve_columns(weihu, "inventory")
    clean, blocked, details = apply_checks(weihu, domain="inventory", col_map=col_map)
    name_blocks = [
        d
        for d in details
        if "material_name" in str(d.get("header") or "")
        or "material_name" in str(d.get("reason_detail") or "")
    ]
    assert name_blocks == [], name_blocks
    assert len(blocked) == 0 or int(blocked["material_name"].map(lambda v: not str(v).strip()).sum() or 0) == 0
    assert (clean["material_name"].astype(str).str.strip() == "南孚电池").sum() >= 3


REAL_305 = Path(__file__).resolve().parents[1] / "data" / "uploads" / "315653e264e9.xlsx"


@pytest.mark.skipif(not REAL_305.exists(), reason="no local 305 workbook")
def test_real_305_weihu_merged_names_filled():
    fc._reload_ledger_route()
    df = load_stock_flow_tabular(REAL_305)
    weihu = df[df["sheet"].astype(str) == "维护材料"]

    def blank(v) -> bool:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return True
        s = str(v).strip()
        return s == "" or s.lower() in {"nan", "none", "null", "-"}

    assert int(weihu["material_name"].map(blank).sum()) == 0
    hit = weihu[
        (weihu["material_name"].astype(str).str.strip() == "南孚电池")
        & (weihu["spec"].astype(str).str.contains("7号", na=False))
    ]
    assert len(hit) >= 1
