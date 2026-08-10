#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-4 smoke: release supersede + diff (RELEASE_DIFF_OK)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_rdiff_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.release_diff import diff_releases, mark_supersede  # noqa: E402


def main() -> int:
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM fact_release_rows")
        for rid, key, qty in [
            ("rel_a", "k1", 1),
            ("rel_a", "k2", 2),
            ("rel_b", "k2", 20),
            ("rel_b", "k3", 3),
        ]:
            con.execute(
                """
                INSERT INTO fact_release_rows
                  (source_release_id, file_id, target_domain, row_key, payload_json)
                VALUES (?, 'f', 'inventory', ?, ?)
                """,
                [rid, key, json.dumps({"qty": qty}, ensure_ascii=False)],
            )
    finally:
        con.close()

    with meta_tx() as m:
        for rid in ("rel_a", "rel_b"):
            m.execute(
                """
                INSERT OR REPLACE INTO release_manifest (
                    release_id, file_id, config_version, staging_id, clean_rows,
                    blocked_rows, material_ops_json, fingerprint, released_by, status
                ) VALUES (?, 'f', 'v1', 'stg', 1, 0, '{}', 'fp', 'smoke', 'released')
                """,
                [rid],
            )

    d = diff_releases("rel_a", "rel_b")
    assert d["counts"]["added"] == 1  # k3
    assert d["counts"]["removed"] == 1  # k1
    assert d["counts"]["changed"] == 1  # k2
    mark_supersede(newer_release_id="rel_b", older_release_id="rel_a", actor="smoke")
    with meta_tx() as m:
        b = m.execute(
            "SELECT supersedes, superseded_by FROM release_manifest WHERE release_id='rel_b'"
        ).fetchone()
        a = m.execute(
            "SELECT supersedes, superseded_by FROM release_manifest WHERE release_id='rel_a'"
        ).fetchone()
    assert b["supersedes"] == "rel_a" and a["superseded_by"] == "rel_b"

    print("RELEASE_DIFF_OK")
    print(d["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
