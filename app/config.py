# -*- coding: utf-8 -*-
"""Runtime config for smart-material-system (Phase A + Stage 1)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
UPLOAD = DATA / "uploads"
UPLOAD_TMP = UPLOAD / "tmp"
RAW = DATA / "raw_evidence"
STAGING = DATA / "staging"
BACKUP = DATA / "backups"
EVAL = DATA / "eval"

META_DB = Path(os.environ.get("META_DB", DATA / "meta.sqlite"))
BIZ_DB = Path(os.environ.get("BIZ_DB", DATA / "material.duckdb"))

# Upload limits (docs/05 §1.4)
UPLOAD_MAX_BYTES = int(os.environ.get("UPLOAD_MAX_BYTES", 2 * 1024**3))
UPLOAD_MAX_FILES = int(os.environ.get("UPLOAD_MAX_FILES", 50))
UPLOAD_MAX_BATCH_BYTES = int(os.environ.get("UPLOAD_MAX_BATCH_BYTES", 4 * 1024**3))
UPLOAD_DIR_QUOTA_BYTES = int(os.environ.get("UPLOAD_DIR_QUOTA_BYTES", 200 * 1024**3))

OPS_TOKEN = os.environ.get("OPS_TOKEN", "dev-ops-token-change-me")
ALLOW_LEGACY_INGEST = os.environ.get("ALLOW_LEGACY_INGEST", "0") == "1"
ALLOW_FREE_QUERY = os.environ.get("ALLOW_FREE_QUERY", "0") == "1"
# F4 LAN 来源限制（docs/11 F4）：逗号分隔 CIDR，如 "192.168.1.0/24,10.0.0.0/8"；
# 空 = 关闭（默认本机绑定 + 全放行）；非空时仅放行回环与命中 CIDR 的客户端 IP
ALLOWED_CIDRS = [c.strip() for c in os.environ.get("ALLOWED_CIDRS", "").split(",") if c.strip()]

TASK_HEARTBEAT_TIMEOUT_SEC = int(os.environ.get("TASK_HEARTBEAT_TIMEOUT_SEC", 30 * 60))
TASK_MAX_ATTEMPTS = int(os.environ.get("TASK_MAX_ATTEMPTS", 3))
WORKER_POLL_SEC = float(os.environ.get("WORKER_POLL_SEC", 1.0))
# UI-3：worker 定时对 metric_group=business 的业务指标写 metric_snapshot（分钟）
METRIC_SNAPSHOT_MINUTES = int(os.environ.get("METRIC_SNAPSHOT_MINUTES", 30))
QUERY_ROW_LIMIT = int(os.environ.get("QUERY_ROW_LIMIT", 200))
# 只读导出端点行数上限（/export/table/*）
EXPORT_ROW_LIMIT = int(os.environ.get("EXPORT_ROW_LIMIT", 100000))

API_V1_PREFIX = "/api/v1"
SPARSE_EVIDENCE_ROWS = int(os.environ.get("SPARSE_EVIDENCE_ROWS", 5000))

# F2: FastAPI hosts Vue dist on same origin (docs/11 §5.1)
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", ROOT / "frontend" / "dist"))

# Stage 1–2 model endpoints (docs/01) — big=:8001; fast=:8000 Stage2+ (7B transition / 9B target)
LLM_BIG_ENDPOINT = os.environ.get("LLM_BIG_ENDPOINT", "http://127.0.0.1:8001/v1")
LLM_FAST_ENDPOINT = os.environ.get("LLM_FAST_ENDPOINT", os.environ.get("LLM_ENDPOINT", "http://127.0.0.1:8000/v1"))
LLM_EMBED_ENDPOINT = os.environ.get("LLM_EMBED_ENDPOINT", "http://127.0.0.1:8002/v1")
LLM_BIG_MODEL = os.environ.get("LLM_BIG_MODEL", "qwen3.6-27b")
# Stage 2 transition name; 9B when weights land (docs/01). Empty env still allowed via LLM_FAST_MODEL=.
LLM_FAST_MODEL = os.environ.get("LLM_FAST_MODEL", "qwen2.5-7b")
LLM_EMBED_MODEL = os.environ.get("LLM_EMBED_MODEL", "qwen3-embedding-0.6b")
LLM_TIMEOUT_SEC = float(os.environ.get("LLM_TIMEOUT_SEC", 300))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", 1))
LLM_CIRCUIT_FAILS = int(os.environ.get("LLM_CIRCUIT_FAILS", 3))
LLM_CIRCUIT_COOLDOWN_SEC = float(os.environ.get("LLM_CIRCUIT_COOLDOWN_SEC", 60))
# Qwen3.6 chat template: disable thinking for SQL/JSON structured tasks (vLLM chat_template_kwargs)
LLM_ENABLE_THINKING = os.environ.get("LLM_ENABLE_THINKING", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# Module 12 Phase B: LLM suggest on flow_pending only (never writes DuckDB)
FLOW_LLM_ENABLED = os.environ.get("FLOW_LLM_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
FLOW_LLM_BATCH = int(os.environ.get("FLOW_LLM_BATCH", 5))
FLOW_LLM_CONFIDENCE_MIN = float(os.environ.get("FLOW_LLM_CONFIDENCE_MIN", 0.55))
# When embed endpoint missing: use lexical recall (Stage 1 PoC)
EMBED_FALLBACK_LEXICAL = os.environ.get("EMBED_FALLBACK_LEXICAL", "1") == "1"

# Ask assistant NL2SQL engine (docs/19 Step1+): legacy | vanna
ASK_ENGINE = os.environ.get("ASK_ENGINE", "legacy").strip().lower()
VANNA_PERSIST_DIR = Path(os.environ.get("VANNA_PERSIST_DIR", str(DATA / "vanna")))
VANNA_AUTO_TRAIN = os.environ.get("VANNA_AUTO_TRAIN", "1") == "1"

# Step4 confirm gate (docs/03 §4.5): block release on quality blockers / unconfirmed plan
INTAKE_GATE_ENFORCE = os.environ.get("INTAKE_GATE_ENFORCE", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
INTAKE_REQUIRE_PLAN_CONFIRM = os.environ.get("INTAKE_REQUIRE_PLAN_CONFIRM", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

def ensure_dirs() -> None:
    """Idempotently create runtime data directories.

    Called lazily by db connections (meta_conn / biz bootstrap) and lifespan,
    NOT at import time — keeps `import app.config` side-effect-free so tests
    can monkeypatch path constants before any directory is created.
    """
    for _d in (DATA, UPLOAD, UPLOAD_TMP, RAW, STAGING, BACKUP, EVAL):
        _d.mkdir(parents=True, exist_ok=True)
    _warn_test_data_dir()


def _warn_test_data_dir() -> None:
    """A1-4: warn if DATA_DIR points at the test sandbox area (misconfig risk).

    Only fires when DATA resolves under ``tests/sandboxes`` — the dedicated
    sandbox root — so pytest's tmp_path (basename starts with ``test_``) and
    the project default ``data/`` do not trigger false positives.
    """
    import warnings

    try:
        sandboxes = (ROOT / "tests" / "sandboxes").resolve()
        data_resolved = DATA.resolve()
        if data_resolved == sandboxes or sandboxes in data_resolved.parents:
            warnings.warn(
                f"DATA_DIR {DATA!s} points at the test sandbox area; "
                "production backups would capture test data. Point DATA_DIR at a "
                "dedicated production directory.",
                stacklevel=2,
            )
    except OSError:
        pass
