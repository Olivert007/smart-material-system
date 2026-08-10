#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: generic lineage_rebuild (LINEAGE_REBUILD_OK)."""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_lineage_smoke_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.staging import staging_payload_path  # noqa: E402
from app.services.writer import lineage_rebuild  # noqa: E402


def main() -> int:
    # Guard: lineage helpers must not UPDATE fact tables in place
    src = (ROOT / "app/services/writer.py").read_text(encoding="utf-8")
    assert "def lineage_rebuild" in src and "def lineage_revoke" in src
    for name in ("lineage_revoke", "lineage_rebuild"):
        m = re.search(rf"def {name}\([\s\S]*?(?=\ndef )", src)
        assert m, name
        assert "UPDATE fact_" not in m.group(0), f"{name} must not UPDATE fact_*"

    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM fact_demand")
    finally:
        con.close()

    fid, rid, sid = "dem_smoke", "rel_dem_smoke", "stg_dem_smoke"
    with meta_tx() as m:
        m.execute(
            """
            INSERT OR REPLACE INTO file_batch
              (file_id, filename, format, sha256, stored_path, status)
            VALUES (?, 'd.xlsx', 'xlsx', ?, '/tmp/d.xlsx', 'released')
            """,
            [fid, fid],
        )
        m.execute(
            """
            INSERT OR REPLACE INTO staging_record (
                staging_id, file_id, config_version, target_domain, source_file_hash,
                status, version, clean_rows, release_id
            ) VALUES (?, ?, 'v1', 'demand', ?, 'RELEASED', 1, 1, ?)
            """,
            [sid, fid, f"{fid}:demand", rid],
        )
        m.execute(
            """
            INSERT OR REPLACE INTO release_manifest (
                release_id, file_id, config_version, staging_id, clean_rows,
                blocked_rows, material_ops_json, fingerprint, released_by, status
            ) VALUES (?, ?, 'v1', ?, 1, 0, '{}', 'fp', 'smoke', 'released')
            """,
            [rid, fid, sid],
        )

    path = staging_payload_path(fid, "v1", "demand")
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"物资名称": "电缆", "物资编码": "D1", "数量": 3, "期次": "2026Q1"}]
    ).to_parquet(path, index=False)

    out = lineage_rebuild(rid, actor="smoke")
    assert out["ok"] and out["target_domain"] == "demand" and out["rows"] == 1, out
    con = writer_conn()
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM fact_demand WHERE source_release_id=?", [rid]
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 1
    print("LINEAGE_REBUILD_OK")
    print(f"domain=demand rows={out['rows']} release_id={rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
