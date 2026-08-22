# -*- coding: utf-8 -*-
"""Static frontend route declaration checks (doc 19)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "frontend" / "src" / "router" / "index.ts"


def _extract_main_paths(content: str) -> set[str]:
    paths: set[str] = set()
    for m in re.finditer(r"\{\s*path:\s*'([^']+)'", content):
        p = m.group(1)
        if ":fileId" in p or p.startswith("/:"):
            continue
        paths.add(p)
    return paths


def _extract_redirect_targets(content: str) -> set[str]:
    targets: set[str] = set()
    for m in re.finditer(r"redirect:\s*(?:\(to\)\s*=>\s*\(\{\s*)?path:\s*'([^']+)'", content):
        targets.add(m.group(1))
    for m in re.finditer(r"redirect:\s*\{\s*path:\s*'([^']+)'", content):
        targets.add(m.group(1))
    return targets


def test_main_routes_cover_core_journey():
    content = ROUTER.read_text(encoding="utf-8")
    main = _extract_main_paths(content)
    required = {"/", "/intake", "/govern", "/data", "/system", "/stage/:fileId", "/trace", "/ask"}
    # stage route uses param — check by prefix
    assert "/" in main
    assert "/intake" in main
    assert "/govern" in main
    assert "/data" in main
    assert "/system" in main
    assert any(p.startswith("/stage/") or p == "/stage/:fileId" for p in main) or "/stage/:fileId" in content


def test_redirect_targets_are_declared():
    content = ROUTER.read_text(encoding="utf-8")
    main = _extract_main_paths(content)
    redirects = _extract_redirect_targets(content)
    for target in redirects:
        assert target in main, f"redirect target {target!r} not in main routes"
