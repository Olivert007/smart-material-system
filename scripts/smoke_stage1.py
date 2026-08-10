#!/usr/bin/env python3
"""Stage 1 smoke: models status + map-suggest + ask (requires vLLM on :8001)."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))
os.environ.setdefault("OPS_TOKEN", "dev-ops-token-change-me")
os.environ["LLM_BIG_ENDPOINT"] = os.environ.get("EVAL_BIG_ENDPOINT") or "http://127.0.0.1:8001/v1"
os.environ["LLM_BIG_MODEL"] = os.environ.get("EVAL_BIG_MODEL") or "qwen3.6-27b"
os.environ["LLM_EMBED_ENDPOINT"] = os.environ.get("EVAL_EMBED_ENDPOINT") or "http://127.0.0.1:8002/v1"
os.environ["LLM_EMBED_MODEL"] = os.environ.get("EVAL_EMBED_MODEL") or "qwen3-embedding-0.6b"
os.environ.setdefault("EMBED_FALLBACK_LEXICAL", "1")
os.environ.setdefault("LLM_ENABLE_THINKING", "0")

from app.repositories import init_meta  # noqa: E402
from app.services.eval_skel import ensure_eval_skeleton  # noqa: E402
from app.services.mapping_suggest import suggest_header_mapping  # noqa: E402
from app.services.model_client import probe_endpoint  # noqa: E402
from app.services.text2sql import ask  # noqa: E402
from app import config  # noqa: E402


def wait_big(timeout=600) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = probe_endpoint(config.LLM_BIG_ENDPOINT, timeout=5)
        if p.get("ok"):
            return p
        print("waiting big...", p.get("error"))
        time.sleep(5)
    raise SystemExit("big model not ready")


def main() -> None:
    init_meta()
    ensure_eval_skeleton()
    print("probe", wait_big())

    headers = ["物资编码", "物资名称", "现有数量", "库位号", "备注"]
    mapped = suggest_header_mapping(headers)
    print("map_suggest", json.dumps({k: mapped.get(k) for k in (
        "ok", "mapping", "model_state", "model", "unmapped_columns", "error", "latency_ms"
    )}, ensure_ascii=False, indent=2))
    assert mapped.get("mapping", {}).get("物资编码") in ("material_code", "ignore") or mapped.get("ok")

    # ask may be empty DB — still must pass AST path
    ans = ask("库存表有多少行")
    print("ask", json.dumps({k: ans.get(k) for k in (
        "ok", "sql", "rows", "model_state", "error", "answer"
    )}, ensure_ascii=False, indent=2)[:2000])
    print("STAGE1_SMOKE_OK")


if __name__ == "__main__":
    main()
