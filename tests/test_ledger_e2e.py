# -*- coding: utf-8 -*-
"""台账样例 E2E：fixture xlsx → 上传 → analyze/confirm（inventory+asset）→ /export/ledger 行数对齐。"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from ledger_xlsx_util import build_ledger_xlsx_from_fixture, expected_row_counts

HEADERS = {"X-Ops-Token": "test-ops"}


@pytest.fixture(autouse=True)
def _ledger_upload_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.govern import flow_config as fc

    fc._reload_ledger_route()
    monkeypatch.delenv("FLOW_CONFIG_DIR", raising=False)
    if hasattr(fc._load_all_configs, "cache_clear"):
        fc._load_all_configs.cache_clear()
    monkeypatch.setattr(config, "UPLOAD_MAX_BYTES", 20 * 1024 * 1024)
    monkeypatch.setattr(config, "UPLOAD_MAX_BATCH_BYTES", 50 * 1024 * 1024)
    monkeypatch.setattr(config, "UPLOAD_DIR_QUOTA_BYTES", 100 * 1024 * 1024)


def _wait_task(client: TestClient, task_id: str, timeout: float = 45.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = client.get(f"/api/v1/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            return t
        time.sleep(0.15)
    raise AssertionError(f"task timeout: {task_id}")


def _analyze_and_confirm(
    client: TestClient,
    file_id: str,
    target_domain: str,
) -> str:
    an = client.post(
        f"/api/v1/intake/analyze/{file_id}",
        json={
            "target_domain": target_domain,
            "include_stage": True,
            "refresh_profile": False,
        },
    )
    assert an.status_code == 200, an.text
    payload = an.json()
    assert payload["ok"] is True, payload
    assert payload["steps"]["stage"]["ok"] is True

    force = not payload.get("gate_ok", True)
    if force:
        pc = client.post(
            f"/api/v1/intake/plan/{file_id}/confirm",
            headers=HEADERS,
            json={
                "force": True,
                "note": "ledger e2e",
                "target_domain": target_domain,
            },
        )
        assert pc.status_code == 200, pc.text

    conf = client.post(
        f"/api/v1/intake/stage/{file_id}/confirm",
        headers=HEADERS,
        json={
            "expected_status": "STAGED",
            "target_domain": target_domain,
            "force": force,
        },
    )
    assert conf.status_code == 200, conf.text
    body = conf.json()
    return body["release"]["release_id"]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_ledger_fixture_intake_export_e2e(client: TestClient) -> None:
    xlsx = build_ledger_xlsx_from_fixture()
    counts = expected_row_counts()
    inv_sheets = {"维护材料", "备品备件", "应急备汛物资"}
    assert counts["维护材料"] == 2
    assert counts["公用工器具"] == 3
    inv_total = sum(counts[s] for s in inv_sheets)

    with xlsx.open("rb") as f:
        up = client.post(
            "/api/v1/files",
            files={
                "file": (
                    xlsx.name,
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert up.status_code == 202, up.text
    body = up.json()
    fid = body["file_id"]
    assert _wait_task(client, body["task_id"])["status"] == "done"

    inv_rel = _analyze_and_confirm(client, fid, "inventory")
    asset_rel = _analyze_and_confirm(client, fid, "asset")

    q_inv = client.post(
        "/api/v1/query",
        headers=HEADERS,
        json={
            "sql": (
                "SELECT COUNT(*) AS c FROM fact_inventory "
                f"WHERE source_release_id='{inv_rel}'"
            )
        },
    )
    assert q_inv.status_code == 200, q_inv.text
    assert q_inv.json()["data"][0]["c"] == inv_total

    q_asset = client.post(
        "/api/v1/query",
        headers=HEADERS,
        json={
            "sql": (
                "SELECT COUNT(*) AS c FROM fact_asset "
                f"WHERE source_release_id='{asset_rel}'"
            )
        },
    )
    assert q_asset.status_code == 200, q_asset.text
    assert q_asset.json()["data"][0]["c"] == counts["公用工器具"]

    for sheet in inv_sheets:
        q_sheet = client.post(
            "/api/v1/query",
            headers=HEADERS,
            json={
                "sql": (
                    "SELECT COUNT(*) AS c FROM fact_inventory "
                    f"WHERE source_release_id='{inv_rel}' AND source_sheet='{sheet}'"
                )
            },
        )
        assert q_sheet.status_code == 200, q_sheet.text
        assert q_sheet.json()["data"][0]["c"] == counts[sheet]

    for sheet, n in counts.items():
        r = client.get(f"/api/v1/export/ledger/{sheet}")
        assert r.status_code == 200, f"{sheet}: {r.text[:300]}"
        lines = [ln for ln in r.text.splitlines() if ln.strip()]
        assert len(lines) >= 2, sheet
        header = lines[0].lstrip("\ufeff")
        if sheet == "公用工器具":
            assert header.startswith("资产编码"), header
        else:
            assert "名称" in header or header.startswith("名称"), header
        if sheet in inv_sheets:
            q_sheet = client.post(
                "/api/v1/query",
                headers=HEADERS,
                json={
                    "sql": (
                        "SELECT COUNT(*) AS c FROM fact_inventory "
                        f"WHERE source_release_id='{inv_rel}' AND source_sheet='{sheet}'"
                    )
                },
            )
            rel_n = q_sheet.json()["data"][0]["c"]
            assert len(lines) - 1 >= rel_n, (sheet, len(lines) - 1, rel_n)
        elif sheet == "公用工器具":
            assert len(lines) - 1 >= n
