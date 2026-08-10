#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2-2 smoke: echarts dependency present for Ask charts (ASK_CHART_OK)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    assert "echarts" in deps, deps.keys()
    ask = (ROOT / "frontend" / "src" / "pages" / "AskView.vue").read_text(encoding="utf-8")
    assert "echarts" in ask and "chartable" in ask and "renderChart" in ask
    print("ASK_CHART_OK")
    print(f"echarts={deps['echarts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
