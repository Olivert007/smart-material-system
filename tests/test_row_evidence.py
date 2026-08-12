# -*- coding: utf-8 -*-
"""行级证据：发布结果行 → 来源原始值 + 规整值 + 血缘链条（optv1/05 Q11）。"""
from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import meta_tx, writer_conn
from app.workers import intake_worker


@pytest.fixture(autouse=True)
def _disable_worker():
    orig = intake_worker.worker.start
    intake_worker.worker.start = lambda: None
    yield
    intake_worker.worker.start = orig


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _seed():
    from app import config

    with meta_tx() as con:
        con.execute(
            "INSERT INTO file_batch (file_id, filename, format, status) VALUES (?, ?, 'xlsx', 'released')",
            ["file-row-1", "台账.xlsx"],
        )
        con.execute(
            """
            INSERT INTO staging_record (
                staging_id, file_id, config_version, target_domain, source_file_hash,
                status, clean_rows, blocked_rows, version, release_id
            ) VALUES (?, ?, ?, ?, ?, 'RELEASED', 2, 0, 1, ?)
            """,
            ["stg-row-1", "file-row-1", "v1", "inventory", "hash-row-1", "rel-row-1"],
        )
        con.execute(
            """
            INSERT INTO release_manifest (
                release_id, file_id, config_version, staging_id, clean_rows, blocked_rows,
                released_by, status
            ) VALUES (?, ?, 'v1', 'stg-row-1', 2, 0, '张三', 'released')
            """,
            ["rel-row-1", "file-row-1"],
        )
        con.execute(
            """
            INSERT INTO intake_task (task_id, file_id, filename, task_type, status, progress)
            VALUES (?, ?, ?, 'intake', 'done', 100)
            """,
            ["task-row-1", "file-row-1", "台账.xlsx"],
        )
        con.execute(
            "INSERT INTO govern_confirm (source, detail, decision, note, actor) VALUES ('map_confirm', ?, 'accepted', '人工确认', '张三')",
            [json.dumps({"file_id": "file-row-1"}, ensure_ascii=False)],
        )
        con.execute(
            "INSERT INTO write_audit (action, release_id, actor, detail_json) VALUES ('intake_release', 'rel-row-1', '张三', ?)",
            [json.dumps({"rows": 2}, ensure_ascii=False)],
        )
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, source, confirmed_by)
            VALUES ('物资名称', 'material_name', 'inventory', 'human_confirm', '张三')
            """,
        )

    # raw 快照（原始值：qty 未清洗）+ 发布载荷 parquet
    staging_dir = config.STAGING / "file-row-1"
    staging_dir.mkdir(parents=True, exist_ok=True)
    raw = pd.DataFrame(
        [
            {"物资名称": "电力电缆", "现有数量": "50+", "单位": "米", "库位": "A1"},
            {"物资名称": "螺栓", "现有数量": "120", "单位": "个", "库位": "B2"},
        ]
    )
    raw.to_parquet(staging_dir / "v1_inventory_raw.parquet", index=False)
    clean = raw.copy()
    clean["现有数量"] = [50, 120]
    clean.to_parquet(staging_dir / "v1_inventory.parquet", index=False)

    con = writer_conn()
    try:
        con.execute(
            """
            INSERT INTO dim_material (material_id, material_code, material_name, spec, unit, category, match_level, source_release_id)
            VALUES ('M-ROW-1', 'MC-1', '电力电缆', 'YJV', '米', '电缆', 'L3', 'rel-row-1')
            """,
        )
        con.execute(
            """
            INSERT INTO fact_inventory (
                inventory_id, material_id, row_key, region, category, source_file, source_sheet,
                stock_qty, unit, location, source_release_id
            ) VALUES ('INV-ROW-1', 'M-ROW-1', ?, '川云', '电缆', '台账.xlsx', '维护材料', 50, '米', 'A1', 'rel-row-1')
            """,
            ["台账.xlsx|inventory|M-ROW-1|1"],
        )
        con.execute(
            """
            INSERT INTO fact_release_rows (source_release_id, file_id, target_domain, row_key, payload_json)
            VALUES ('rel-row-1', 'file-row-1', 'inventory', ?, ?)
            """,
            [
                "台账.xlsx|inventory|M-ROW-1|1",
                json.dumps(
                    {
                        "inventory_id": "INV-ROW-1",
                        "material_id": "M-ROW-1",
                        "row_key": "台账.xlsx|inventory|M-ROW-1|1",
                        "region": "川云",
                        "category": "电缆",
                        "source_file": "台账.xlsx",
                        "source_sheet": "维护材料",
                        "stock_qty": 50,
                        "unit": "米",
                        "location": "A1",
                        "source_release_id": "rel-row-1",
                    },
                    ensure_ascii=False,
                ),
            ],
        )
    finally:
        con.close()


def test_row_evidence_raw_to_clean(client):
    _seed()
    r = client.get(
        "/api/v1/govern/lineage/row",
        params={"release_id": "rel-row-1", "row_key": "台账.xlsx|inventory|M-ROW-1|1"},
    )
    assert r.status_code == 200, r.text[:500]
    body = r.json()
    assert body["source_file"] == "台账.xlsx"
    assert body["source_sheet"] == "维护材料"
    assert body["release"]["released_by"] == "张三"
    assert body["staging"]["config_version"] == "v1"
    assert body["task"]["status"] == "done"
    assert body["material"]["match_level"] == "L3"
    # 原始值 → 规整值对照：qty 50+ → 50
    qty = [c for c in body["compare"] if c["field"] == "stock_qty"]
    assert qty and qty[0]["raw_value"] == "50+" and qty[0]["clean_value"] == 50
    assert qty[0]["changed"] is True
    # 物资名称在主数据表，由 material_id 关联；对照表保留 material_id
    assert any(c["field"] == "material_id" for c in body["compare"])
    # 字段映射 + 规则依据 + 审计
    assert {"std_field": "material_name", "source_header": "物资名称"} in body["mapping"]
    assert any(h["header"] == "物资名称" for h in body["rule_hits"])
    assert any(a["action"] == "intake_release" for a in body["audit"])


def test_row_evidence_not_found(client):
    _seed()
    r = client.get(
        "/api/v1/govern/lineage/row",
        params={"release_id": "rel-row-1", "row_key": "nope"},
    )
    assert r.status_code == 404
