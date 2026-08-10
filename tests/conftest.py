# -*- coding: utf-8 -*-
"""pytest 全局测试环境固化（治理方案 question/05 修复方案）。

背景：app.config 在 import 时读 env 并绑定常量；全量运行下先被收集的测试模块决定绑定值，
后续模块的 env 设置全部失效（Q-1~Q-4），且 DATA_DIR 全局共享（Q-5）。
本 conftest：
1. 收集期（任何测试模块 import 之前）设置统一测试 env，并立即导入 app.config 锁定绑定；
2. autouse fixture 为每个用例隔离数据目录（monkeypatch config 路径常量）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- 统一测试 env：必须在任何测试模块 import app.config 之前固化 ----
os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp(prefix="sms_ct_")) / "data")
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.15"
os.environ["LLM_MAX_RETRIES"] = "2"
os.environ["LLM_CIRCUIT_FAILS"] = "99"
os.environ["TASK_HEARTBEAT_TIMEOUT_SEC"] = "60"
os.environ["TASK_MAX_ATTEMPTS"] = "3"
os.environ["UPLOAD_MAX_FILES"] = "2"
os.environ["UPLOAD_MAX_BATCH_BYTES"] = "1000"
os.environ["UPLOAD_DIR_QUOTA_BYTES"] = "500"
os.environ["UPLOAD_MAX_BYTES"] = "400"
os.environ["INTAKE_GATE_ENFORCE"] = "1"
os.environ["INTAKE_REQUIRE_PLAN_CONFIRM"] = "0"
os.environ["EMBED_FALLBACK_LEXICAL"] = "1"
os.environ["LLM_BIG_ENDPOINT"] = ""
os.environ["LLM_FAST_ENDPOINT"] = ""

import pytest  # noqa: E402
from app import config  # noqa: E402  # 强制在此刻绑定上方 env，锁定测试配置


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例独立数据目录：覆盖 config 路径常量，杜绝用例间共享污染（Q-5）。"""
    d = tmp_path
    monkeypatch.setattr(config, "DATA", d)
    monkeypatch.setattr(config, "UPLOAD", d / "uploads")
    monkeypatch.setattr(config, "UPLOAD_TMP", d / "uploads" / "tmp")
    monkeypatch.setattr(config, "RAW", d / "raw_evidence")
    monkeypatch.setattr(config, "STAGING", d / "staging")
    monkeypatch.setattr(config, "BACKUP", d / "backups")
    monkeypatch.setattr(config, "EVAL", d / "eval")
    monkeypatch.setattr(config, "META_DB", d / "meta.sqlite")
    monkeypatch.setattr(config, "BIZ_DB", d / "material.duckdb")
    for p in (
        config.UPLOAD,
        config.UPLOAD_TMP,
        config.RAW,
        config.STAGING,
        config.BACKUP,
        config.EVAL,
    ):
        p.mkdir(parents=True, exist_ok=True)
