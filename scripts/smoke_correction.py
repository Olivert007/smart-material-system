#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2-4 smoke: correction_request → new release + supersede (CORRECTION_OK)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_corr_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services import correction_gov as cg  # noqa: E402


def main() -> int:
    init_meta()
    older = "rel_old_smoke"
    with meta_tx() as m:
        m.execute(
            """
            INSERT INTO release_manifest (
                release_id, file_id, config_version, staging_id, clean_rows, blocked_rows,
                released_by, status
            ) VALUES (?, 'f1', '1', 'st1', 1, 0, 'smoke', 'released')
            """,
            [older],
        )
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        payload = {
            "inventory_id": "i1",
            "material_id": "M1",
            "stock_qty": 10,
            "quota_qty": 20,
            "category": "轴承",
            "source_file": "f1",
        }
        con.execute(
            """
            INSERT INTO fact_release_rows
              (source_release_id, file_id, target_domain, row_key, payload_json)
            VALUES (?, 'f1', 'inventory', 'i1', ?)
            """,
            [older, json.dumps(payload, ensure_ascii=False)],
        )
        con.execute(
            """
            INSERT INTO fact_inventory
              (inventory_id, material_id, category, source_file, stock_qty, quota_qty, source_release_id)
            VALUES ('i1', 'M1', '轴承', 'f1', 10, 20, ?)
            """,
            [older],
        )
    finally:
        con.close()

    prop = cg.propose(
        release_id=older,
        row_key="i1",
        field="stock_qty",
        value_new="42",
        reason="smoke",
        actor="smoke",
    )
    assert prop["ok"], prop
    out = cg.apply(prop["correction_id"], actor="smoke")
    assert out["ok"] and out["supersedes"] == older, out
    new_rel = out["new_release_id"]

    con = writer_conn()
    try:
        row = con.execute(
            "SELECT payload_json FROM fact_release_rows WHERE source_release_id=? AND row_key='i1'",
            [new_rel],
        ).fetchone()
        assert row is not None
        payload2 = json.loads(row[0])
        assert float(payload2["stock_qty"]) == 42, payload2
        inv = con.execute(
            "SELECT stock_qty, source_release_id FROM fact_inventory WHERE inventory_id='i1'"
        ).fetchone()
        assert float(inv[0]) == 42 and inv[1] == new_rel, inv
    finally:
        con.close()

    with meta_tx() as m:
        man_old = m.execute(
            "SELECT superseded_by FROM release_manifest WHERE release_id=?", [older]
        ).fetchone()
        man_new = m.execute(
            "SELECT supersedes FROM release_manifest WHERE release_id=?", [new_rel]
        ).fetchone()
        assert man_old["superseded_by"] == new_rel
        assert man_new["supersedes"] == older
        corr = m.execute(
            "SELECT status FROM correction_request WHERE correction_id=?",
            [prop["correction_id"]],
        ).fetchone()
        assert corr["status"] == "applied"

    print("CORRECTION_OK")
    print(f"new_release={new_rel} stock_qty=42")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
