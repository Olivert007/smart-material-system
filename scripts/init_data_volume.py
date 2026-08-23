# -*- coding: utf-8 -*-
"""Seed data into empty data volume on first start (doc 21 O5)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path


def init_data_volume(data_dir: Path, seed_dir: Path) -> dict:
    """Copy seed files into data dir if missing. Existing files are not overwritten."""
    copied: list[str] = []
    skipped: list[str] = []
    if not seed_dir.is_dir():
        return {"copied_seed_files": copied, "skipped_existing": skipped}

    for src in sorted(seed_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(seed_dir)
        dst = data_dir / rel
        if dst.exists():
            skipped.append(str(rel))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(str(rel))
    return {"copied_seed_files": copied, "skipped_existing": skipped}


def main() -> int:
    import os

    root = Path(__file__).resolve().parents[1]
    data_dir = Path(os.environ.get("DATA_DIR", root / "data"))
    seed_dir = Path(os.environ.get("SEED_DIR", root / "seed"))
    result = init_data_volume(data_dir, seed_dir)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
