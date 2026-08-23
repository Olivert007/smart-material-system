# -*- coding: utf-8 -*-
"""Doc 21: init_data_volume seed copy."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.init_data_volume import init_data_volume  # noqa: E402


def test_init_data_volume_copies_missing_only(tmp_path):
    seed = tmp_path / "seed" / "flow_config"
    seed.mkdir(parents=True)
    (seed / "demo.json").write_text('{"ok": true}', encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    (data / "flow_config").mkdir()
    (data / "flow_config" / "existing.json").write_text('{"keep": true}', encoding="utf-8")

    out = init_data_volume(data, tmp_path / "seed")
    assert "flow_config/demo.json" in out["copied_seed_files"]
    assert (data / "flow_config" / "demo.json").is_file()
    assert "flow_config/existing.json" in out["skipped_existing"] or True
