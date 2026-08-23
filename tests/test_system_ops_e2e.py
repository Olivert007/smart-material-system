# -*- coding: utf-8 -*-
"""系统运维页端到端测试（optv3/system-page-review.md 验收闭环）。

覆盖 /system 页三块 Tab 的后端完整流程：
1. 系统状态：health/ready、ops/tasks、ops/alerts（演示数据不产生失败告警）、备份、恢复演练。
2. 模型状态：models/status 结构、models/{role}/activate|restart 鉴权与审计。
3. 本地设置：写操作（备份/演练/模型操作）必须带操作令牌，未带返回 401。
"""
from __future__ import annotations

import os

os.environ["OPS_TOKEN"] = "test-ops"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.workers import intake_worker  # noqa: E402


@pytest.fixture(autouse=True)
def _disable_worker():
    # 与 test_routes_smoke 一致：禁用后台 Worker，避免 DuckDB 读写竞态干扰断言。
    orig = intake_worker.worker.start
    intake_worker.worker.start = lambda: None
    yield
    intake_worker.worker.start = orig


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


OPS = {"X-Ops-Token": "test-ops"}


# ---------- 系统状态：健康检查 ----------

def test_health_live(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "live"


def test_health_ready_fields(client):
    r = client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    # 系统状态页分项检查所需的字段必须齐全（模型状态走独立 models/status 接口）
    for key in ("status", "version", "meta_db", "biz_db", "worker", "frontend_dist"):
        assert key in body, f"health/ready 缺少字段 {key}"


# ---------- 系统状态：任务队列 + 告警 ----------

def test_ops_tasks_summary_fields(client):
    r = client.get("/api/v1/ops/tasks")
    assert r.status_code == 200
    body = r.json()
    for key in ("pending", "processing", "done", "failed", "by_status"):
        assert key in body, f"ops/tasks 缺少字段 {key}"
    assert isinstance(body["pending"], int) and isinstance(body["failed"], int)


def test_ops_alerts_empty_without_failed_tasks(client):
    """核心验收：无 failed 任务时，告警区必须为空（演示数据不得制造失败告警）。"""
    r = client.get("/api/v1/ops/alerts")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] == []
    assert body["count"] == 0
    assert not any(a.get("rule") == "task_failed" for a in body["active"])


def test_ops_alerts_detect_failed_tasks(client):
    """反向证明：确实存在 failed 任务时，告警逻辑会正常给出 task_failed。"""
    from app.repositories import meta_conn

    con = meta_conn()
    try:
        # intake_task.file_id 外键引用 file_batch，需先建 file_batch 记录
        con.execute(
            "INSERT INTO file_batch (file_id, filename, format, status) VALUES ('e2e-f1', 'demo-missing.csv', 'csv', 'uploaded')"
        )
        con.execute(
            """
            INSERT INTO intake_task (task_id, file_id, filename, task_type, status, progress, message)
            VALUES ('e2e-fail-1', 'e2e-f1', 'demo-missing.csv', 'parse_evidence', 'failed', 100, '文件不存在')
            """
        )
        con.commit()
    finally:
        con.close()
    r = client.get("/api/v1/ops/alerts")
    assert r.status_code == 200
    active = r.json()["active"]
    assert any(a["rule"] == "task_failed" for a in active), f"未生成 task_failed 告警: {active}"


# ---------- 模型状态 ----------

def test_models_status_structure(client):
    r = client.get("/api/v1/models/status")
    assert r.status_code == 200
    body = r.json()
    # 模型全未启动时 stage=0（dev_ok）；有模型在线时 stage=1/2。结构上仅要求合法整数。
    assert "stage" in body and isinstance(body["stage"], int) and body["stage"] in (0, 1, 2)
    for role in ("big", "fast", "embed"):
        item = body[role]
        assert "configured_model" in item and "ok" in item
    assert "lexical_fallback" in body["embed"]


def test_models_activate_requires_token(client):
    r = client.post("/api/v1/models/big/activate")
    assert r.status_code == 401
    assert r.json()["code"] == "OPS_AUTH_REQUIRED"


def test_models_activate_with_token_and_audit(client):
    r = client.post("/api/v1/models/big/activate", headers=OPS)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 审计落库
    from app.repositories import meta_conn

    con = meta_conn()
    try:
        row = con.execute(
            "SELECT action, actor FROM write_audit WHERE action=? ORDER BY audit_id DESC LIMIT 1",
            ["model_activate_big"],
        ).fetchone()
        assert row is not None, "激活操作未写入 write_audit"
        assert row["action"] == "model_activate_big"
        assert row["actor"] == "ops"
    finally:
        con.close()


def test_models_restart_requires_token(client):
    r = client.post("/api/v1/models/embed/restart")
    assert r.status_code == 401


def test_models_restart_with_token_and_audit(client):
    r = client.post("/api/v1/models/fast/restart", headers=OPS)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    from app.repositories import meta_conn

    con = meta_conn()
    try:
        row = con.execute(
            "SELECT action FROM write_audit WHERE action=? ORDER BY audit_id DESC LIMIT 1",
            ["model_restart_fast"],
        ).fetchone()
        assert row is not None, "重启操作未写入 write_audit"
    finally:
        con.close()


def test_models_activate_invalid_role(client):
    r = client.post("/api/v1/models/unknown/activate", headers=OPS)
    assert r.status_code == 400
    assert r.json()["code"] == "BAD_ROLE"


# ---------- 本地设置：备份与恢复演练 ----------

def test_ops_backup_requires_token(client):
    r = client.post("/api/v1/ops/backup")
    assert r.status_code == 401


def test_ops_backup_and_list_roundtrip(client):
    r = client.post("/api/v1/ops/backup", headers=OPS)
    assert r.status_code == 200
    backup_id = r.json()["backup_id"]
    assert backup_id

    # 备份出现在列表最前
    r = client.get("/api/v1/ops/backups")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and items[0]["backup_id"] == backup_id


def test_ops_restore_drill_requires_token(client):
    r = client.post("/api/v1/ops/restore-drill", json={"note": "e2e"})
    assert r.status_code == 401


def test_ops_restore_drill_roundtrip(client):
    # 后端 note/result/backup_id 为 query 参数（与前端 client.ts 一致）
    r = client.post(
        "/api/v1/ops/restore-drill",
        headers=OPS,
        params={"note": "e2e 演练", "result": "ok"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get("/api/v1/ops/restore-drill")
    assert r.status_code == 200
    body = r.json()
    assert body["recorded"] is True
    assert body["record"]["note"] == "e2e 演练"


# ---------- 系统状态：LLM 调用统计 ----------

def test_ops_llm_cost_fields(client):
    r = client.get("/api/v1/ops/llm-cost")
    assert r.status_code == 200
    body = r.json()
    for key in ("days", "total_calls", "ok_calls", "failed_calls", "by_day"):
        assert key in body, f"ops/llm-cost 缺少字段 {key}"
