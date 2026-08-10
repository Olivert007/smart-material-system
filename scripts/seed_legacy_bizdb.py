#!/usr/bin/env python3
"""Seed biz DB from legacy 物资库.duckdb (adds source_release_id='legacy_seed')."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402

LEGACY_DEFAULT = Path("/workspace/2026-07/data/物资库.duckdb")
TABLES = [
    "dim_material",
    "fact_inventory",
    "fact_asset",
    "fact_demand",
    "fact_quota_adjust",
    "fact_stock_flow",
]


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else LEGACY_DEFAULT
    if not src.exists():
        raise SystemExit(f"legacy db not found: {src}")
    if config.BIZ_DB.exists():
        bak = config.BIZ_DB.with_suffix(".duckdb.bak")
        shutil.copy2(config.BIZ_DB, bak)
        print(f"backed up existing biz db -> {bak}")
        config.BIZ_DB.unlink()

    # copy file then migrate
    shutil.copy2(src, config.BIZ_DB)
    con = duckdb.connect(str(config.BIZ_DB))
    try:
        ensure_biz_schema(con)
        for t in TABLES:
            con.execute(f"UPDATE {t} SET source_release_id = 'legacy_seed' WHERE source_release_id IS NULL")
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n}")
    finally:
        con.close()
    print(f"seeded {config.BIZ_DB}")


if __name__ == "__main__":
    main()
