# -*- coding: utf-8 -*-
"""HI-R18: tabular numeric coercion for parquet-safe multi-sheet concat."""
from __future__ import annotations

import pandas as pd
import pytest

from app.services.intake.evidence import (
    coerce_tabular_for_parquet,
    save_evidence,
    tabular_path,
)


def test_mixed_numeric_column_coerced():
    df = pd.DataFrame({"asset_qty": [1.0, "2", 3, "/"], "sheet": ["a", "a", "b", "b"]})
    out = coerce_tabular_for_parquet(df)
    assert pd.api.types.is_numeric_dtype(out["asset_qty"])
    assert out["asset_qty"].tolist()[:3] == [1.0, 2.0, 3.0]
    out.to_parquet("/tmp/sms_r18_probe.parquet", index=False)


def test_slash_not_zero():
    out = coerce_tabular_for_parquet(pd.DataFrame({"replace_cycle": ["/", "3", "/"]}))
    vals = out["replace_cycle"].tolist()
    assert pd.isna(vals[0])
    assert vals[1] == 3.0
    assert pd.isna(vals[2])
    assert vals[0] != 0


def test_save_evidence_mixed_types(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "RAW", tmp_path)
    mixed = pd.DataFrame({"asset_qty": [1.0, "1"], "material_name": ["a", "b"]})
    cell = pd.DataFrame(
        [{"file_id": "fid", "sheet": "s", "row": 1, "col": "A", "raw_value": "1", "value_type": "str"}]
    )
    save_evidence(cell, "fid", tabular=mixed)
    path = tabular_path("fid")
    assert path.exists()
    loaded = pd.read_parquet(path)
    assert pd.api.types.is_numeric_dtype(loaded["asset_qty"])
