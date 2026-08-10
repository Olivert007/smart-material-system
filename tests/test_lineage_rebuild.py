# -*- coding: utf-8 -*-
"""PR7: generic lineage_rebuild for inventory (D6) — no in-place UPDATE."""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_lineage_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.staging import staging_payload_path  # noqa: E402
from app.services.writer import (  # noqa: E402
    lineage_rebuild,
    lineage_revoke,
    list_releases,
)


def _assert_no_inplace_update() -> None:
    src = (ROOT / "app/services/writer.py").read_text(encoding="utf-8")
    # Within lineage_* helpers: forbid UPDATE on fact_* quantity/stock columns
    # Static: no "UPDATE fact_" in writer lineage path (delete+insert only)
    for m in re.finditer(r"def lineage_(revoke|rebuild)\([\s\S]*?(?=\ndef )", src):
        block = m.group(0)
        assert "UPDATE fact_" not in block, "lineage must not UPDATE fact_* in place"
        assert "UPDATE fact_inventory SET" not in block


def _seed_inventory_release() -> str:
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        con.execute("DELETE FROM fact_inventory")
        con.execute("DELETE FROM dim_material WHERE source_release_id LIKE 'rel_inv_%'")
    finally:
        con.close()

    suffix = uuid.uuid4().hex[:8]
    fid = f"inv_lineage_{suffix}"
    rid = f"rel_inv_{suffix}"
    sid = f"stg_inv_{suffix}"
    with meta_tx() as m:
        m.execute(
            """
            INSERT INTO file_batch (file_id, filename, format, sha256, stored_path, status)
            VALUES (?, 'inv.xlsx', 'xlsx', ?, '/tmp/inv.xlsx', 'released')
            """,
            [fid, fid],
        )
        m.execute(
            """
            INSERT INTO staging_record (
                staging_id, file_id, config_version, target_domain, source_file_hash,
                status, version, clean_rows, release_id
            ) VALUES (?, ?, 'v1', 'inventory', ?, 'RELEASED', 1, 2, ?)
            """,
            [sid, fid, f"{fid}:inventory", rid],
        )
        m.execute(
            """
            INSERT INTO release_manifest (
                release_id, file_id, config_version, staging_id, clean_rows,
                blocked_rows, material_ops_json, fingerprint, released_by, status
            ) VALUES (?, ?, 'v1', ?, 2, 0, '{}', 'fp', 'seed', 'released')
            """,
            [rid, fid, sid],
        )

    path = staging_payload_path(fid, "v1", "inventory")
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"物资名称": "螺丝", "物资编码": "SC01", "现有数量": 10, "区域": "A"},
            {"物资名称": "垫片", "物资编码": "SC02", "现有数量": 5, "区域": "B"},
        ]
    ).to_parquet(path, index=False)

    # Plant wrong published rows (will be replaced by rebuild)
    con = writer_conn()
    try:
        con.execute(
            """
            INSERT INTO dim_material
              (material_id, material_code, material_name, source_file, code_source, match_level, source_release_id)
            VALUES ('SC01', 'SC01', '旧名', 'inv.xlsx', '', 'L3', ?)
            """,
            [rid],
        )
        con.execute(
            """
            INSERT INTO fact_inventory
              (inventory_id, material_id, region, category, source_file, stock_qty, source_release_id)
            VALUES ('bad1', 'SC01', 'X', '未分类', 'inv.xlsx', 999, ?)
            """,
            [rid],
        )
    finally:
        con.close()
    return rid


def test_rebuild_inventory_replaces_rows() -> None:
    rid = _seed_inventory_release()
    out = lineage_rebuild(rid, actor="tester")
    assert out["ok"] and out["rebuilt"] and out["target_domain"] == "inventory"
    assert out["rows"] == 2, out

    con = writer_conn()
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM fact_inventory WHERE source_release_id=?", [rid]
        ).fetchone()[0]
        bad = con.execute(
            "SELECT COUNT(*) FROM fact_inventory WHERE inventory_id='bad1'"
        ).fetchone()[0]
        qty = con.execute(
            "SELECT stock_qty FROM fact_inventory WHERE material_id='SC01'"
        ).fetchone()[0]
        name = con.execute(
            "SELECT material_name FROM dim_material WHERE material_id='SC01'"
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 2 and bad == 0
    assert float(qty) == 10.0
    assert name == "螺丝"

    with meta_tx() as m:
        audits = m.execute(
            "SELECT action FROM write_audit WHERE release_id=? ORDER BY audit_id DESC",
            [rid],
        ).fetchall()
    actions = [a["action"] for a in audits]
    assert "lineage_rebuild" in actions


def test_revoke_then_list() -> None:
    rid = _seed_inventory_release()
    lineage_rebuild(rid, actor="t1")
    rev = lineage_revoke(rid, actor="t2")
    assert rev["ok"] and rev["deleted_rows"] == 2
    con = writer_conn()
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM fact_inventory WHERE source_release_id=?", [rid]
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 0
    listed = list_releases(domain="inventory")
    assert any(i["release_id"] == rid for i in listed["items"])


def main() -> None:
    _assert_no_inplace_update()
    print("OK static_no_update")
    test_rebuild_inventory_replaces_rows()
    print("OK rebuild_inventory")
    test_revoke_then_list()
    print("OK revoke_list")
    print("LINEAGE_REBUILD_OK")


if __name__ == "__main__":
    main()
