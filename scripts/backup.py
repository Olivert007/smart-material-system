#!/usr/bin/env python3
"""Create a consistent backup batch (pauses writer)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories import init_meta  # noqa: E402
from app.services.backup import create_backup  # noqa: E402


def main() -> None:
    init_meta()
    tag = sys.argv[1] if len(sys.argv) > 1 else None
    result = create_backup(tag=tag)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
