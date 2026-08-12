# -*- coding: utf-8 -*-
"""optv1/04 规则资产：启用/停用/预演/冲突/审计/幂等。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import meta_conn, meta_tx
from app.services.govern import rule_dict as rule_dict_svc
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


def _seed_rule(header: str = "物资名称", std_field: str = "material_name", domain: str = "inventory"):
    with meta_tx() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO rule_dict
              (header, std_field, business_domain, hits, source, confirmed_by, status)
            VALUES (?, ?, ?, 5, 'human_confirm', 'tester', 'active')
            """,
            [header, std_field, domain],
        )
        row = con.execute(
            "SELECT rule_id FROM rule_dict WHERE header=? AND business_domain=? AND std_field=?",
            [header, domain, std_field],
        ).fetchone()
    return int(row["rule_id"])


def _seed_pending(header: str = "物资名称"):
    with meta_tx() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO file_batch (file_id, filename, format, status)
            VALUES ('file-rule-1', 'demo.xlsx', 'xlsx', 'evidence_done')
            """
        )
        con.execute(
            """
            INSERT OR REPLACE INTO map_pending
              (pending_id, file_id, sheet, header, suggested_field, candidates_json,
               reason, status, business_domain)
            VALUES ('mp-rule-1', 'file-rule-1', 'Sheet1', ?, 'material_name',
                    '[{"std_field":"material_name","score":0.9}]', 'low_confidence',
                    'pending', 'inventory')
            """,
            [header],
        )


def test_rule_list_includes_status_and_pending_hits(client):
    rule_id = _seed_rule()
    _seed_pending()
    r = client.get("/api/v1/assets/rule-dict?limit=50")
    assert r.status_code == 200
    items = r.json()["items"]
    hit = [it for it in items if it["rule_id"] == rule_id][0]
    assert hit["status"] == "active"
    assert hit["pending_map_hits"] >= 1


def test_rule_preview_and_disable_enable(client):
    rule_id = _seed_rule()
    _seed_pending()

    r = client.post(f"/api/v1/assets/rule-dict/{rule_id}/preview")
    assert r.status_code == 200
    preview = r.json()
    assert preview["dry_run"] is True
    assert preview["affected_rows"] >= 1
    assert preview["rebuild_needed"] is False

    r = client.post(
        f"/api/v1/assets/rule-dict/{rule_id}/confirm",
        json={"action": "disable", "note": "停用旧规则"},
        headers={"X-Ops-Token": "test-ops"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is False
    assert body["next_status"] == "disabled"

    with meta_conn() as con:
        row = con.execute(
            "SELECT status, changed_by FROM rule_dict WHERE rule_id=?", [rule_id]
        ).fetchone()
        audit = con.execute(
            "SELECT decision, actor FROM govern_confirm WHERE source='rule_dict_status'"
        ).fetchone()
    assert row["status"] == "disabled"
    assert row["changed_by"] == "ops"
    assert audit["decision"] == "disable"

    # 停用后 lookup 不再命中该规则
    hit = rule_dict_svc.lookup_header("物资名称", business_domain="inventory")
    assert hit is None

    r = client.post(
        f"/api/v1/assets/rule-dict/{rule_id}/confirm",
        json={"action": "enable"},
        headers={"X-Ops-Token": "test-ops"},
    )
    assert r.json()["next_status"] == "active"
    hit = rule_dict_svc.lookup_header("物资名称", business_domain="inventory")
    assert hit is not None and hit["std_field"] == "material_name"


def test_rule_confirm_requires_ops(client):
    rule_id = _seed_rule()
    r = client.post(
        f"/api/v1/assets/rule-dict/{rule_id}/confirm",
        json={"action": "disable"},
    )
    assert r.status_code == 401


def test_rule_confirm_idempotent(client):
    rule_id = _seed_rule()
    payload = {"action": "disable", "idempotency_key": "rule-idem-1"}
    r1 = client.post(
        f"/api/v1/assets/rule-dict/{rule_id}/confirm",
        json=payload,
        headers={"X-Ops-Token": "test-ops"},
    )
    r2 = client.post(
        f"/api/v1/assets/rule-dict/{rule_id}/confirm",
        json=payload,
        headers={"X-Ops-Token": "test-ops"},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json().get("idempotent") is not True
    assert r2.json().get("idempotent") is True
    assert r2.json().get("idempotency_replay") is True


def test_rule_conflicts_view(client):
    _seed_rule("设备名称", "asset_name", "inventory")
    _seed_rule("设备名称", "material_name", "inventory")
    r = client.get("/api/v1/assets/rule-dict/conflicts")
    assert r.status_code == 200
    body = r.json()
    assert body["conflict_count"] == 1
    assert body["conflicts"][0]["fields"] == ["asset_name", "material_name"]
