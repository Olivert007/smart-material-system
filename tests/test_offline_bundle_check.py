# -*- coding: utf-8 -*-
"""Doc 21: offline bundle checks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_offline_bundle import check_offline_bundle  # noqa: E402


def test_offline_bundle_check_structure():
    manifest = ROOT / "deploy" / "offline-manifest.example.json"
    out = check_offline_bundle(manifest, ROOT)
    assert "dockerignore" in out
    assert "build_assets" in out
    assert "wheelhouse_or_dist" in out["build_assets"]
    assert isinstance(out["ok"], bool)
