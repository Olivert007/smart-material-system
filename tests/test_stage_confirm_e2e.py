# -*- coding: utf-8 -*-
"""规整确认页端到端：按域 GET staging / 中文 quality / 确认写入当前可见域。"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"X-Ops-Token": "test-ops"}
CSV = (
    "物资编码,物资名称,现有数量,单位\n"
    "A1,电缆,10,个\n"
    "A2,螺栓,20,个\n"
)


@pytest.fixture(autouse=True)
def _upload_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "UPLOAD_MAX_BYTES", 20 * 1024 * 1024)
    monkeypatch.setattr(config, "UPLOAD_MAX_BATCH_BYTES", 50 * 1024 * 1024)
    monkeypatch.setattr(config, "UPLOAD_DIR_QUOTA_BYTES", 100 * 1024 * 1024)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _wait_task(client: TestClient, task_id: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = client.get(f"/api/v1/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            return t
        time.sleep(0.15)
    raise AssertionError(f"task timeout: {task_id}")


def _upload(client: TestClient) -> str:
    up = client.post(
        "/api/v1/files",
        files={"file": ("stage_e2e.csv", CSV.encode("utf-8"), "text/csv")},
    )
    assert up.status_code == 202, up.text
    body = up.json()
    assert _wait_task(client, body["task_id"])["status"] == "done", body
    return body["file_id"]


def _stage(client: TestClient, file_id: str, domain: str) -> dict:
    r = client.post(
        f"/api/v1/intake/stage/{file_id}",
        json={"config_version": "v1", "target_domain": domain},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _get_stage(client: TestClient, file_id: str, domain: str | None = None) -> tuple[int, dict]:
    params = {"target_domain": domain} if domain else None
    r = client.get(f"/api/v1/intake/stage/{file_id}", params=params)
    return r.status_code, r.json() if r.content else {}


def test_files_list_exposes_filename_for_stage_title(client: TestClient) -> None:
    fid = _upload(client)
    listed = client.get("/api/v1/files?limit=100").json()
    hit = next((x for x in listed["items"] if x["file_id"] == fid), None)
    assert hit is not None
    assert hit["filename"] == "stage_e2e.csv"


def test_get_stage_and_blocked_filter_by_target_domain(client: TestClient) -> None:
    fid = _upload(client)
    inv = _stage(client, fid, "inventory")
    asset = _stage(client, fid, "asset")
    assert inv["staging_id"] != asset["staging_id"]
    assert inv.get("dry_run", {}).get("target_domain") == "inventory"
    assert asset.get("dry_run", {}).get("target_domain") == "asset"

    st_inv, body_inv = _get_stage(client, fid, "inventory")
    st_asset, body_asset = _get_stage(client, fid, "asset")
    st_latest, body_latest = _get_stage(client, fid, None)
    assert st_inv == 200 and st_asset == 200 and st_latest == 200
    assert body_inv["staging_id"] == inv["staging_id"]
    assert body_asset["staging_id"] == asset["staging_id"]
    assert body_latest["staging_id"] == asset["staging_id"], "无域参数应返回最新一条"

    q_inv = (body_inv.get("dry_run") or {}).get("quality") or {}
    q_asset = (body_asset.get("dry_run") or {}).get("quality") or {}
    assert q_inv.get("domain") == "inventory"
    assert q_asset.get("domain") == "asset"
    assert body_inv.get("clean_rows") is not None
    assert body_asset.get("clean_rows") is not None

    bl_inv = client.get(
        f"/api/v1/stats/quality/{fid}/blocked", params={"target_domain": "inventory", "limit": 50}
    )
    bl_asset = client.get(
        f"/api/v1/stats/quality/{fid}/blocked", params={"target_domain": "asset", "limit": 50}
    )
    assert bl_inv.status_code == 200 and bl_asset.status_code == 200
    assert bl_inv.json()["staging_id"] == inv["staging_id"]
    assert bl_asset.json()["staging_id"] == asset["staging_id"]


def test_quality_in_staging_is_zh(client: TestClient) -> None:
    fid = _upload(client)
    _stage(client, fid, "inventory")
    _, body = _get_stage(client, fid, "inventory")
    quality = (body.get("dry_run") or {}).get("quality") or {}
    hint = str(quality.get("hint") or "")
    blob = hint + " " + " ".join(str(i.get("detail") or "") for i in quality.get("issues_sample") or [])
    assert "blocking=true" not in blob
    assert "required group blank" not in blob
    assert "LLM" not in blob
    assert not re.search(r"\bconfirm\b", blob, re.I)
    assert not re.search(r"key=.+count=", blob, re.I)


def test_confirm_without_domain_writes_latest_not_visible_inventory(client: TestClient) -> None:
    """复现 StageView 漏传 target_domain：页面看库存，写入却落到最新的资产 staging。"""
    fid = _upload(client)
    inv = _stage(client, fid, "inventory")
    asset = _stage(client, fid, "asset")
    assert inv["staging_id"] != asset["staging_id"]

    r = client.post(
        f"/api/v1/intake/stage/{fid}/confirm",
        headers=HEADERS,
        json={
            "version": inv["version"],
            "expected_status": "STAGED",
            "force": True,
        },
    )
    assert r.status_code == 200, r.text
    _, after_inv = _get_stage(client, fid, "inventory")
    _, after_asset = _get_stage(client, fid, "asset")
    # 当前错误行为：无域 confirm 命中最新 asset
    assert after_asset["status"] == "RELEASED"
    assert after_inv["status"] == "STAGED"


def test_confirm_with_target_domain_writes_visible_inventory(client: TestClient) -> None:
    fid = _upload(client)
    inv = _stage(client, fid, "inventory")
    _stage(client, fid, "asset")

    r = client.post(
        f"/api/v1/intake/stage/{fid}/confirm",
        headers=HEADERS,
        json={
            "version": inv["version"],
            "expected_status": "STAGED",
            "target_domain": "inventory",
            "staging_id": inv["staging_id"],
            "force": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("target_domain") == "inventory" or r.json().get("target_table") == "fact_inventory"
    _, after_inv = _get_stage(client, fid, "inventory")
    _, after_asset = _get_stage(client, fid, "asset")
    assert after_inv["status"] == "RELEASED"
    assert after_asset["status"] == "STAGED"


def test_stage_view_and_client_pass_current_domain_on_confirm() -> None:
    vue = (ROOT / "frontend/src/pages/StageView.vue").read_text(encoding="utf-8")
    client_ts = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")
    assert "getIntakeQuality" not in vue
    assert "/intake/quality/" not in vue
    assert "displayFilename" in vue
    assert "issueCountsSummary" in vue
    assert "sanitizeUserHint" in vue
    assert "getStaging(props.fileId, targetDomain.value)" in vue
    assert "高级信息" not in vue and "接入计划" not in vue
    assert "去治理中心" not in vue
    assert "target_domain: targetDomain.value" in vue
    confirm_fn = client_ts.split("export async function confirmStaging")[1].split(
        "export async function healthLive"
    )[0]
    assert "target_domain: opts?.target_domain" in confirm_fn
    assert "staging_id: opts?.staging_id" in confirm_fn
