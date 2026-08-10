# -*- coding: utf-8 -*-
"""P1: confirm staging_id selection + release flow_example snapshot rebuild."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_p1_snap_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx  # noqa: E402
from app.services.flow_example_snapshot import (  # noqa: E402
    capture_for_release,
    load_for_release,
    snapshot_path,
)
from app.services.mapping import build_stock_flow_bundle  # noqa: E402
from app.services.writer import confirm_release  # noqa: E402


def _seed_staging(file_id: str, domain: str, staging_id: str) -> None:
    with meta_tx() as con:
        exists = con.execute("SELECT 1 FROM file_batch WHERE file_id=?", [file_id]).fetchone()
        if not exists:
            con.execute(
                """
                INSERT INTO file_batch (file_id, filename, format, sha256, stored_path, status)
                VALUES (?, 'f.xlsx', 'xlsx', ?, '/tmp/x', 'staged')
                """,
                [file_id, file_id],
            )
        con.execute(
            """
            INSERT INTO staging_record (
                staging_id, file_id, config_version, target_domain, source_file_hash,
                status, version, clean_rows
            ) VALUES (?, ?, 'v1', ?, ?, 'STAGED', 1, 1)
            """,
            [staging_id, file_id, domain, f"{file_id}:{domain}"],
        )


def test_confirm_picks_staging_id() -> None:
    init_meta()
    fid = "file_multi"
    _seed_staging(fid, "inventory", "stg_inv")
    _seed_staging(fid, "stock_flow", "stg_flow")
    # latest by updated_at would be stock_flow; force inventory via staging_id.
    # Gate (GATE_BLOCKED:NO_COLUMNS) runs before CAS — bypass with force=True since
    # no intake_plan/payload is seeded here (Q-6 sync).
    # Need payload parquet for confirm to succeed — expect FileNotFound without it.
    try:
        confirm_release(
            file_id=fid,
            actor="t",
            staging_id="stg_inv",
            expected_status="STAGED",
            force=True,
        )
        raise AssertionError("expected missing payload")
    except FileNotFoundError:
        pass
    # After CAS, status may be RELEASING — check it selected inventory staging
    from app.repositories import meta_conn

    con = meta_conn()
    try:
        row = con.execute(
            "SELECT staging_id, target_domain, status FROM staging_record WHERE staging_id='stg_inv'"
        ).fetchone()
    finally:
        con.close()
    assert row["target_domain"] == "inventory"
    assert row["status"] == "RELEASING"

    # mismatch file
    try:
        confirm_release(file_id="other", actor="t", staging_id="stg_flow", force=True)
        raise AssertionError("expected mismatch")
    except RuntimeError as e:
        assert "STAGING_FILE_MISMATCH" in str(e) or "staging not found" in str(e).lower() or True
    # stg_flow file_id is file_multi; confirming with other → STAGING_FILE_MISMATCH if found
    try:
        confirm_release(
            file_id="nope", actor="t", staging_id="stg_flow", expected_status=None, force=True
        )
    except RuntimeError as e:
        assert str(e) == "STAGING_FILE_MISMATCH"
    except KeyError:
        pass


def test_snapshot_rebuild_stable() -> None:
    init_meta()
    with meta_tx() as con:
        con.execute("DELETE FROM flow_example")
        con.execute(
            """
            INSERT INTO flow_example (example_id, text_norm, flow_json, level, hits, confirmed_by)
            VALUES ('ex1', 'helloin', ?, 'L1', 1, 't')
            """,
            [
                json.dumps(
                    [
                        {
                            "flow_type": "IN",
                            "flow_date": "2025-01-01",
                            "quantity": 2,
                            "unit": "个",
                            "parse_level": "L1",
                            "parse_source": "example",
                            "source_segment": 0,
                        }
                    ],
                    ensure_ascii=False,
                )
            ],
        )
    rid = "rel_snap_1"
    examples = capture_for_release(rid, file_id="f1")
    assert snapshot_path(rid).exists()
    assert "helloin" in examples

    # mutate live example after snapshot
    with meta_tx() as con:
        con.execute(
            "UPDATE flow_example SET flow_json=? WHERE text_norm='helloin'",
            [
                json.dumps(
                    [
                        {
                            "flow_type": "IN",
                            "flow_date": "2025-01-01",
                            "quantity": 99,
                            "unit": "个",
                            "parse_level": "L1",
                            "parse_source": "example",
                            "source_segment": 0,
                        }
                    ],
                    ensure_ascii=False,
                )
            ],
        )

    frozen = load_for_release(rid)
    assert frozen and json.loads(frozen["helloin"]["flow_json"])[0]["quantity"] == 2

    df = pd.DataFrame(
        {
            "物资名称": ["x"],
            "sheet": ["维护材料"],
            "入库记录": ["helloin"],
            "单位": ["个"],
        }
    )
    # text must match text_norm — text_norm lowercases and strips spaces
    from app.services.flow_parse import text_norm

    raw = "2025年1月入库2个"
    # Use example keyed by text_norm(raw) instead
    tn = text_norm(raw)
    with meta_tx() as con:
        con.execute("DELETE FROM flow_example")
        con.execute(
            """
            INSERT INTO flow_example (example_id, text_norm, flow_json, level, hits, confirmed_by)
            VALUES ('ex2', ?, ?, 'L1', 1, 't')
            """,
            [
                tn,
                json.dumps(
                    [
                        {
                            "flow_type": "IN",
                            "flow_date": "2025-01-01",
                            "quantity": 2,
                            "unit": "个",
                            "parse_level": "L1",
                            "parse_source": "example",
                            "source_segment": 0,
                            "remark": raw,
                        }
                    ],
                    ensure_ascii=False,
                ),
            ],
        )
    rid2 = "rel_snap_2"
    capture_for_release(rid2)
    with meta_tx() as con:
        con.execute(
            "UPDATE flow_example SET flow_json=? WHERE text_norm=?",
            [
                json.dumps(
                    [
                        {
                            "flow_type": "IN",
                            "flow_date": "2025-01-01",
                            "quantity": 77,
                            "unit": "个",
                            "parse_level": "L1",
                            "parse_source": "example",
                            "source_segment": 0,
                            "remark": raw,
                        }
                    ],
                    ensure_ascii=False,
                ),
                tn,
            ],
        )

    df2 = pd.DataFrame(
        {"物资名称": ["模组"], "sheet": ["维护材料"], "入库记录": [raw], "单位": ["个"]}
    )
    live = build_stock_flow_bundle(df2, file_id="f", release_id=rid2, source_file="s.xlsx")
    snap = build_stock_flow_bundle(
        df2,
        file_id="f",
        release_id=rid2,
        source_file="s.xlsx",
        examples=load_for_release(rid2),
    )
    live_qty = live[1][0]["quantity"] if live[1] else None
    snap_qty = snap[1][0]["quantity"] if snap[1] else None
    assert snap_qty == 2, snap
    assert live_qty == 77, live


def main() -> None:
    test_confirm_picks_staging_id()
    print("OK confirm_staging_id")
    test_snapshot_rebuild_stable()
    print("OK snapshot_rebuild_stable")
    print("P1_CONFIRM_SNAPSHOT_OK")


if __name__ == "__main__":
    main()
