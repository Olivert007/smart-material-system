# -*- coding: utf-8 -*-
"""单文件级联删除。

删除一个文件及其全部衍生数据，保持与 writer 现有删除语义一致
（按 source_release_id delete-and-replace，见 app/services/infra/writer.py）：

- writer 库：该文件所有 release 发布的 fact_* / fact_release_rows / dim_material
- meta 库：staging_record、staging_blocked、release_manifest、flow_pending、
  intake_report、intake_task、map_pending、master_pending（按 release）
- 物理文件：uploads 源文件、raw_evidence parquet、staging 目录

删除为不可逆操作，前端须二次确认并提示会连带删除已发布业务数据。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app import config
from app.repositories import acquire_writer, meta_conn, meta_tx, writer_conn

# writer 库中按 source_release_id 关联、需随文件一起删除的表
_RELEASE_TABLES = [
    "fact_release_rows",
    "fact_inventory",
    "fact_asset",
    "fact_demand",
    "fact_quota_adjust",
    "fact_stock_flow",
    "dim_material",
]


def _remove_physical(file_id: str, *, stored_path: str | None) -> list[str]:
    """删除源文件、证据 parquet 与 staging 目录，返回实际删除路径列表。"""
    removed: list[str] = []
    targets: list[Path] = []
    if stored_path:
        p = Path(stored_path)
        if p.exists():
            targets.append(p)
    else:
        targets.extend(config.UPLOAD.glob(f"{file_id}.*"))
    targets.append(config.RAW / f"{file_id}.parquet")
    targets.append(config.RAW / f"{file_id}.tabular.parquet")
    for p in targets:
        try:
            if p.exists():
                p.unlink()
                removed.append(str(p))
        except OSError:
            pass
    staging_dir = config.STAGING / file_id
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
        removed.append(str(staging_dir))
    return removed


def delete_file(file_id: str, *, actor: str = "ops") -> dict[str, Any]:
    """删除单个文件及其级联数据，返回各层清理统计。文件不存在时抛 FileNotFoundError。"""
    if not file_id:
        raise ValueError("file_id required")

    # 1) 读取文件信息与关联的 release_id（staging_record + release_manifest）
    con = meta_conn()
    try:
        fb = con.execute("SELECT * FROM file_batch WHERE file_id=?", [file_id]).fetchone()
        if not fb:
            raise FileNotFoundError(f"file {file_id} not found")
        release_ids = [
            r["release_id"]
            for r in con.execute(
                "SELECT DISTINCT release_id FROM staging_record "
                "WHERE file_id=? AND release_id IS NOT NULL",
                [file_id],
            )
        ]
        release_ids += [
            r["release_id"]
            for r in con.execute(
                "SELECT release_id FROM release_manifest WHERE file_id=?", [file_id]
            )
        ]
        release_ids = list(dict.fromkeys(release_ids))
    finally:
        con.close()

    # 2) writer 库：删除该文件所有 release 发布的事实数据与物料
    deleted_fact = 0
    lock = acquire_writer()
    try:
        wcon = writer_conn()
        try:
            for rid in release_ids:
                for table in _RELEASE_TABLES:
                    # duckdb cursor.rowcount 对 DELETE 不可靠（恒 -1），先计数再删除
                    n = wcon.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE source_release_id = ?",
                        [rid],
                    ).fetchone()[0]
                    wcon.execute(
                        f"DELETE FROM {table} WHERE source_release_id = ?", [rid]
                    )
                    if table != "dim_material":
                        deleted_fact += int(n or 0)
        finally:
            wcon.close()
    finally:
        lock.release()

    # 3) 物理文件 + meta 库记录
    files_removed = _remove_physical(file_id, stored_path=fb["stored_path"])

    with meta_tx() as mcon:
        mcon.execute("DELETE FROM staging_blocked WHERE file_id=?", [file_id])
        mcon.execute("DELETE FROM staging_record WHERE file_id=?", [file_id])
        mcon.execute("DELETE FROM release_manifest WHERE file_id=?", [file_id])
        mcon.execute("DELETE FROM flow_pending WHERE file_id=?", [file_id])
        mcon.execute("DELETE FROM intake_report WHERE file_id=?", [file_id])
        mcon.execute("DELETE FROM intake_task WHERE file_id=?", [file_id])
        mcon.execute("DELETE FROM map_pending WHERE file_id=?", [file_id])
        if release_ids:
            ph = ",".join("?" * len(release_ids))
            mcon.execute(
                f"DELETE FROM master_pending WHERE source_release_id IN ({ph})",
                release_ids,
            )
        mcon.execute("DELETE FROM file_batch WHERE file_id=?", [file_id])
        mcon.execute(
            "INSERT INTO write_audit (action, release_id, actor, detail_json) "
            "VALUES ('file_delete', ?, ?, ?)",
            [
                file_id,
                actor,
                json.dumps(
                    {
                        "releases": release_ids,
                        "deleted_fact_rows": deleted_fact,
                    },
                    ensure_ascii=False,
                ),
            ],
        )

    return {
        "ok": True,
        "file_id": file_id,
        "filename": fb["filename"],
        "releases_removed": release_ids,
        "deleted_fact_rows": deleted_fact,
        "files_removed": files_removed,
    }
