# -*- coding: utf-8 -*-
"""P0-3: flow_config drives stock_flow column resolve + parse separators."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_flow_cfg_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
CFG = TMP / "flow_config"
CFG.mkdir()
os.environ["DATA_DIR"] = str(TMP)
os.environ["FLOW_CONFIG_DIR"] = str(CFG)
os.environ["OPS_TOKEN"] = "test-ops"

# Custom sheet header not in static ALIASES for flow_in_text
(CFG / "demo_sheet.json").write_text(
    json.dumps(
        {
            "source_sheet": "演示台账",
            "aliases": ["demo_alias_sheet"],
            "flow_columns": [
                {
                    "header": "入库流水原文",
                    "flow_type": "IN",
                    "qty_column": "入库数",
                    "unit_column": "计量",
                    "separators": ["；", ";", "|"],
                },
                {
                    "header": "出库流水原文",
                    "flow_type": "OUT",
                    "qty_column": "出库数",
                    "unit_column": "计量",
                    "separators": ["；", ";"],
                },
            ],
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta  # noqa: E402
from app.services.govern.flow_config import (  # noqa: E402
    ensure_flow_configs_seed,
    get_flow_config,
    flow_column_for,
)
from app.services.govern.mapping import build_stock_flow_bundle, resolve_columns  # noqa: E402
from app.services.govern.flow_parse import parse_flow_cell  # noqa: E402


def setup() -> None:
    init_meta()
    r = ensure_flow_configs_seed()
    assert r["ok"] and r["files"] >= 1, r
    assert get_flow_config("演示台账") is not None


def test_get_and_resolve() -> None:
    setup()
    cfg = get_flow_config("演示台账")
    assert cfg and cfg["source_sheet"] == "演示台账"
    assert get_flow_config("demo_alias_sheet") is not None
    assert get_flow_config("前缀_演示台账_后缀") is not None  # contains match

    df = pd.DataFrame(
        {
            "物资名称": ["跳线"],
            "入库流水原文": ["2025年6月入库2条"],
            "入库数": ["2"],
            "出库流水原文": ["2025年7月出库1条"],
            "出库数": ["1"],
            "计量": ["条"],
        }
    )
    # Without config sheet → ALIASES miss custom headers
    m0 = resolve_columns(df, "stock_flow", source_sheet="unknown_sheet")
    assert "flow_in_text" not in m0 or m0.get("flow_in_text") != "入库流水原文"

    m = resolve_columns(df, "stock_flow", source_sheet="演示台账")
    assert m.get("flow_in_text") == "入库流水原文", m
    assert m.get("flow_out_text") == "出库流水原文", m
    assert m.get("qty_in") == "入库数", m
    assert m.get("qty_out") == "出库数", m
    assert m.get("unit") == "计量", m


def test_bundle_uses_separators() -> None:
    setup()
    df = pd.DataFrame(
        {
            "物资名称": ["模块"],
            "sheet": ["演示台账"],
            "入库流水原文": ["2025年1月入库1个|2025年2月入库2个"],
            "入库数": [None],
            "计量": ["个"],
        }
    )
    _table, rows, pending, stats = build_stock_flow_bundle(
        df, file_id="f1", release_id="r1", source_file="demo.xlsx"
    )
    assert stats.get("config_hits", 0) >= 1, stats
    # pipe separator from config should split into 2 segments
    total_segs = len(rows) + len(pending)
    assert total_segs >= 2, (rows, pending, stats)

    fcol = flow_column_for(get_flow_config("演示台账"), "IN")
    segs = parse_flow_cell(
        "2025年1月入库1个|2025年2月入库2个",
        flow_type="IN",
        separators=list(fcol["separators"]),
    )
    assert len(segs) == 2, segs


def main() -> None:
    test_get_and_resolve()
    print("OK get_and_resolve")
    test_bundle_uses_separators()
    print("OK bundle_uses_separators")
    print("P0_3_OK")


if __name__ == "__main__":
    main()
