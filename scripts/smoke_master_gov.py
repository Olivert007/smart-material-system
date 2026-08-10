#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: master_pending + master_apply (MASTER_GOV_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_master_smoke_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.master_gov import confirm_pending, list_pending, propose_from_dim  # noqa: E402


def main() -> int:
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM dim_material")
        con.execute(
            """
            INSERT INTO dim_material
              (material_id, material_code, material_name, spec, match_level, code_source)
            VALUES ('M_SMOKE', 'SM1', '冒烟物料', '1', 'L3', '')
            """
        )
    finally:
        con.close()
    with meta_tx() as m:
        m.execute("DELETE FROM master_pending WHERE material_id='M_SMOKE'")

    out = propose_from_dim()
    assert out["enqueued"] >= 1, out
    pid = list_pending()["items"][0]["pending_id"]
    confirm_pending(pending_id=pid, decision="approve", actor="smoke")
    con = writer_conn()
    try:
        row = con.execute(
            "SELECT code_source, match_level FROM dim_material WHERE material_id='M_SMOKE'"
        ).fetchone()
    finally:
        con.close()
    assert row and row[0] == "master_confirm" and row[1] == "approved", row
    print("MASTER_GOV_OK")
    print(f"enqueued={out['enqueued']} approved=M_SMOKE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
