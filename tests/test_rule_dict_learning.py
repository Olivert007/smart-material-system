# -*- coding: utf-8 -*-
"""P0-2: rule_dict is read by suggest + resolve_columns (docs/04 §6)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_rule_dict_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"
# Force lexical path — no live embed required for this unit test
os.environ["EMBED_FALLBACK_LEXICAL"] = "1"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx  # noqa: E402
from app.services.govern.mapping import resolve_columns  # noqa: E402
from app.services.mapping_suggest import suggest_header_mapping  # noqa: E402
from app.services.govern.rule_dict import dict_prefill  # noqa: E402


def _seed_rules() -> None:
    init_meta()
    with meta_tx() as con:
        con.execute("DELETE FROM rule_dict")
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('账面结存数', 'stock_qty', 'inventory', 3, 'human_confirm', 'tester')
            """
        )
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('品名全称', 'item_name', 'inventory', 2, 'human_confirm', 'tester')
            """
        )
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('序号', 'ignore', 'default', 5, 'human_confirm', 'tester')
            """
        )
        # norm match: stored without spaces / paren noise
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('入库记录', 'flow_in_text', 'stock_flow', 1, 'human_confirm', 'tester')
            """
        )
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('模糊列', 'location', 'inventory', 2, 'human_confirm', 'tester')
            """
        )
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('模糊列', 'region', 'inventory', 2, 'human_confirm', 'tester')
            """
        )


def test_suggest_prefers_rule_dict() -> None:
    _seed_rules()
    headers = ["品名全称", "账面结存数", "序号"]
    res = suggest_header_mapping(headers, business_domain="inventory")
    assert res["ok"]
    assert res["mapping"]["品名全称"] == "item_name"
    assert res["mapping"]["账面结存数"] == "stock_qty"
    assert res["mapping"]["序号"] == "ignore"
    assert res["model_state"] == "rule_dict_hit"
    assert res["model_invoked"] is False
    assert res["model_request_attempted"] is False
    assert "品名全称" in res["dict_hits"]


def test_resolve_columns_overrides_aliases() -> None:
    _seed_rules()
    df = pd.DataFrame(
        {
            "品名全称": ["跳线"],
            "账面结存数": [3],
            "单位": ["条"],
            "物资名称": ["应被字典列覆盖"],
        }
    )
    m = resolve_columns(df, "inventory")
    assert m.get("material_name") == "品名全称", m
    assert m.get("stock_qty") == "账面结存数", m
    assert m.get("unit") == "单位", m


def test_norm_match_and_conflict() -> None:
    _seed_rules()
    prefill, hits, conflicts = dict_prefill(["模糊列"], business_domain="inventory")
    assert "模糊列" in conflicts
    assert "模糊列" not in prefill

    # paren / whitespace normalized against stored「入库记录」
    prefill2, hits2, _ = dict_prefill(["入库记录（ZW备注）"], business_domain="stock_flow")
    assert prefill2.get("入库记录（ZW备注）") == "flow_in_text", (prefill2, hits2)
    assert hits2["入库记录（ZW备注）"]["source"] == "norm"

    df = pd.DataFrame({"模糊列": ["A区"], "物资名称": ["x"], "数量": [1]})
    m = resolve_columns(df, "inventory")
    assert m.get("location") != "模糊列"
    assert m.get("region") != "模糊列"


def main() -> None:
    test_suggest_prefers_rule_dict()
    print("OK suggest_prefers_rule_dict")
    test_resolve_columns_overrides_aliases()
    print("OK resolve_columns_overrides_aliases")
    test_norm_match_and_conflict()
    print("OK norm_match_and_conflict")
    print("P0_2_OK")


if __name__ == "__main__":
    main()
