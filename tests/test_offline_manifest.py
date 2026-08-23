# -*- coding: utf-8 -*-
"""Doc 21: offline manifest parseability."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_offline_manifest_example_parses():
    path = ROOT / "deploy" / "offline-manifest.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "images" in data
    assert "models" in data
    assert len(data["models"]) >= 3
