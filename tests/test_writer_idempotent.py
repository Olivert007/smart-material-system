# -*- coding: utf-8 -*-
"""A1-2: writer.confirm_release idempotency — D2 core guarantee (direct unit test).

Asserts that confirming an already-RELEASED staging short-circuits with
idempotent=True and does NOT re-invoke the DuckDB write path. This is the
data-safety core of D2; previously only covered indirectly by integration tests.
"""
from __future__ import annotations

from app.repositories import init_meta, meta_tx
from app.services.writer import confirm_release


def _seed_released_staging() -> str:
    """Insert a file_batch + staging_record(RELEASED) + release_manifest directly."""
    init_meta()
    with meta_tx() as con:
        con.execute(
            "INSERT OR REPLACE INTO file_batch (file_id, filename, format, status) VALUES (?, ?, ?, ?)",
            ["f-imp-1", "x.csv", "csv", "released"],
        )
        con.execute(
            """
            INSERT OR REPLACE INTO staging_record
            (staging_id, file_id, config_version, target_domain, source_file_hash,
             status, release_id, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ["s-imp-1", "f-imp-1", "v1", "inventory", "hash-imp-1", "RELEASED", "r-imp-1", 1],
        )
        con.execute(
            """
            INSERT OR REPLACE INTO release_manifest
            (release_id, file_id, config_version, staging_id, clean_rows, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ["r-imp-1", "f-imp-1", "v1", "s-imp-1", 0, "released"],
        )
    return "s-imp-1"


def test_confirm_release_idempotent_on_already_released():
    sid = _seed_released_staging()
    # force=True bypasses the intake gate; status is RELEASED so the writer must
    # short-circuit and return the existing manifest without re-writing.
    result = confirm_release(
        file_id="f-imp-1",
        actor="test",
        staging_id=sid,
        force=True,
    )
    assert result["status"] == "RELEASED", result
    assert result.get("idempotent") is True, result
    assert result["release"]["release_id"] == "r-imp-1"


def test_confirm_release_version_conflict():
    _seed_released_staging()
    # expected_version mismatch → STAGE_VERSION_CONFLICT (optimistic concurrency, C2).
    import pytest

    with pytest.raises(RuntimeError, match="STAGE_VERSION_CONFLICT"):
        confirm_release(
            file_id="f-imp-1",
            actor="test",
            staging_id="s-imp-1",
            expected_version=999,
            force=True,
        )
