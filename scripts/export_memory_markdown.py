#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export governance memory Markdown snapshots (docs/20 Step2).

用法：
  PYTHONPATH=. python3 scripts/export_memory_markdown.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.memory_export import export_memory_markdown  # noqa: E402


def main() -> int:
    out = export_memory_markdown()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
