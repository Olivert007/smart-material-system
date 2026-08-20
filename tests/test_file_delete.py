# -*- coding: utf-8 -*-
"""单文件级联删除：服务层 delete_file + 路由 DELETE /files/{file_id}。

覆盖：发布数据（writer 库 fact_*）、规整记录、待办、物理文件的级联清理，
以及未授权/文件不存在等边界。删除为不可逆操作，须二次确认（前端约束）。
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["OPS_TOKEN"] = "test-ops"

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories import (  # noqa: E402
    acquire_writer,
    init_meta,
    meta_conn,
    meta_tx,
    writer_conn,
)
from app.services.intake.file_removal import delete_file  # noqa: E402
from app.workers import intake_worker  # noqa: E402

FILE_ID = "f-del-1"
RELEASE_ID = "r-del-1"


@pytest.fixture(autouse=True)
def _disable_worker():
    """禁用后台 intake worker，避免与删除操作竞争同一文件/数据库。"""
    orig = intake_worker.worker.start
    intake_worker.worker.start = lambda: None
    yield
    intake_worker.worker.start = orig


def _seed_file(file_id: str = FILE_ID, *, with_release: bool = True) -> None:
    """直接构造一个已上传（可含已发布 release）的文件及其全部关联数据。"""
    init_meta()
    with meta_tx() as con:
        con.execute(
            "INSERT OR REPLACE INTO file_batch (file_id, filename, format, status, rows) "
            "VALUES (?, ?, ?, ?, ?)",
            [file_id, "样本.xlsx", "xlsx", "released" if with_release else "uploaded", 3],
        )
        con.execute(
            "INSERT OR REPLACE INTO staging_record "
            "(staging_id, file_id, config_version, target_domain, source_file_hash, "
            "status, release_id, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [f"s-{file_id}", file_id, "v1", "inventory", "hash-del-1",
             "RELEASED" if with_release else "staged",
             RELEASE_ID if with_release else None, 1],
        )
        con.execute(
            "INSERT INTO flow_pending (pending_id, file_id, text_raw, status) VALUES (?, ?, ?, ?)",
            [f"p-{file_id}", file_id, "X", "pending"],
        )
        con.execute(
            "INSERT INTO intake_report (report_id, file_id, report_type, payload_json) "
            "VALUES (?, ?, ?, ?)",
            [f"rep-{file_id}", file_id, "quality_precheck", "{}"],
        )
        con.execute(
            "INSERT INTO intake_task (task_id, file_id, task_type, status) VALUES (?, ?, ?, ?)",
            [f"t-{file_id}", file_id, "intake", "done"],
        )
        con.execute(
            "INSERT INTO staging_blocked (block_id, staging_id, file_id, target_domain, "
            "reason_code) VALUES (?, ?, ?, ?, ?)",
            [f"b-{file_id}", f"s-{file_id}", file_id, "inventory", "missing_header"],
        )
        con.execute(
            "INSERT INTO map_pending (pending_id, file_id, sheet, header, reason, "
            "business_domain) VALUES (?, ?, ?, ?, ?, ?)",
            [f"m-{file_id}", file_id, "S1", "数量", "missing mapping", "default"],
        )
        if with_release:
            con.execute(
                "INSERT OR REPLACE INTO release_manifest "
                "(release_id, file_id, config_version, staging_id, clean_rows, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [RELEASE_ID, file_id, "v1", f"s-{file_id}", 3, "released"],
            )
            con.execute(
                "INSERT INTO master_pending (pending_id, material_id, material_code, "
                "material_name, source_release_id, match_level) VALUES (?, ?, ?, ?, ?, ?)",
                [f"mp-{file_id}", f"mat-{file_id}", "C-1", "电缆", RELEASE_ID, "L3"],
            )
    if with_release:
        lock = acquire_writer()
        try:
            con = writer_conn()
            try:
                con.execute(
                    "INSERT INTO fact_release_rows (source_release_id, file_id, "
                    "target_domain, row_key, payload_json) VALUES (?, ?, ?, ?, ?)",
                    [RELEASE_ID, file_id, "inventory", "k1", "{}"],
                )
                con.execute(
                    "INSERT INTO fact_inventory (inventory_id, material_id, row_key, "
                    "source_file, source_release_id, stock_qty) VALUES (?, ?, ?, ?, ?, ?)",
                    ["inv-del-1", "mat-del-1", "k1", "样本.xlsx", RELEASE_ID, 10],
                )
            finally:
                con.close()
        finally:
            lock.release()
    # 物理文件
    config.UPLOAD.mkdir(parents=True, exist_ok=True)
    (config.UPLOAD / f"{file_id}.xlsx").write_bytes(b"x")
    config.RAW.mkdir(parents=True, exist_ok=True)
    (config.RAW / f"{file_id}.parquet").write_bytes(b"p")
    (config.RAW / f"{file_id}.tabular.parquet").write_bytes(b"t")
    (config.STAGING / file_id).mkdir(parents=True, exist_ok=True)
    (config.STAGING / file_id / "v1_inventory.parquet").write_bytes(b"v")


def _meta_count(table: str, where: str, param: str) -> int:
    con = meta_conn()
    try:
        return int(con.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", [param]).fetchone()[0])
    finally:
        con.close()


def _biz_count(table: str, release_id: str) -> int:
    lock = acquire_writer()
    try:
        con = writer_conn()
        try:
            return int(
                con.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE source_release_id = ?",
                    [release_id],
                ).fetchone()[0]
            )
        finally:
            con.close()
    finally:
        lock.release()


def test_delete_file_cascades_all_layers():
    _seed_file()
    result = delete_file(FILE_ID, actor="tester")
    assert result["ok"] is True
    assert result["filename"] == "样本.xlsx"
    assert result["releases_removed"] == [RELEASE_ID]
    assert result["deleted_fact_rows"] == 2  # fact_release_rows + fact_inventory

    # meta 层全部清空
    for table, where in (
        ("file_batch", "file_id"),
        ("staging_record", "file_id"),
        ("staging_blocked", "file_id"),
        ("release_manifest", "file_id"),
        ("flow_pending", "file_id"),
        ("intake_report", "file_id"),
        ("intake_task", "file_id"),
        ("map_pending", "file_id"),
    ):
        assert _meta_count(table, f"{where}=?", FILE_ID) == 0, table
    assert _meta_count("master_pending", "source_release_id=?", RELEASE_ID) == 0

    # 审计留痕
    con = meta_conn()
    try:
        audit = con.execute(
            "SELECT * FROM write_audit WHERE release_id=?", [FILE_ID]
        ).fetchone()
    finally:
        con.close()
    assert audit is not None and audit["action"] == "file_delete" and audit["actor"] == "tester"

    # writer 层发布数据已删除
    assert _biz_count("fact_release_rows", RELEASE_ID) == 0
    assert _biz_count("fact_inventory", RELEASE_ID) == 0

    # 物理文件已删除
    assert not (config.UPLOAD / f"{FILE_ID}.xlsx").exists()
    assert not (config.RAW / f"{FILE_ID}.parquet").exists()
    assert not (config.RAW / f"{FILE_ID}.tabular.parquet").exists()
    assert not (config.STAGING / FILE_ID).exists()


def test_delete_file_without_release_keeps_other_files():
    # 仅上传、未发布规整的文件：不影响其他文件的发布数据
    _seed_file("f-del-2", with_release=False)
    _seed_file("f-del-3", with_release=True)
    result = delete_file("f-del-2")
    assert result["ok"] is True
    assert result["releases_removed"] == []
    assert _meta_count("file_batch", "file_id=?", "f-del-2") == 0
    # 另一个文件及其发布数据不受影响
    assert _meta_count("file_batch", "file_id=?", "f-del-3") == 1
    assert _biz_count("fact_inventory", RELEASE_ID) == 1


def test_delete_file_not_found():
    init_meta()
    with pytest.raises(FileNotFoundError):
        delete_file("f-no-such")


def test_delete_endpoint_requires_ops_token():
    with TestClient(app) as c:
        r = c.delete(f"/api/v1/files/{FILE_ID}")
        assert r.status_code == 401


def test_delete_endpoint_cascades_via_api():
    _seed_file()
    with TestClient(app) as c:
        r = c.delete(f"/api/v1/files/{FILE_ID}", headers={"X-Ops-Token": "test-ops"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["releases_removed"] == [RELEASE_ID]
    assert _meta_count("file_batch", "file_id=?", FILE_ID) == 0


def test_delete_endpoint_not_found():
    with TestClient(app) as c:
        r = c.delete("/api/v1/files/f-no-such", headers={"X-Ops-Token": "test-ops"})
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


def test_delete_full_chain_via_api():
    """真实链路：上传 CSV → 台账可见 → DELETE → 台账与物理文件均消失。"""
    with TestClient(app) as c:
        content = "物资名称,数量,单位\n光纤跳线,12,条\n光模块,4,个\n".encode("utf-8")
        r = c.post("/api/v1/files", files={"file": ("chain.csv", content, "text/csv")})
        assert r.status_code == 202, r.text
        file_id = r.json()["file_id"]
        assert any(i["file_id"] == file_id for i in c.get("/api/v1/files").json()["items"])

        d = c.delete(f"/api/v1/files/{file_id}", headers={"X-Ops-Token": "test-ops"})
        assert d.status_code == 200, d.text
        assert d.json()["ok"] is True

        after = c.get("/api/v1/files").json()
        assert all(i["file_id"] != file_id for i in after["items"])
        assert not (config.UPLOAD / f"{file_id}.csv").exists()
