# -*- coding: utf-8 -*-
"""Doc 21: .dockerignore policy."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_offline_bundle import check_dockerignore  # noqa: E402


def test_dockerignore_has_required_entries():
    result = check_dockerignore(ROOT)
    assert result["ok"] is True, f"missing: {result['missing']}"
