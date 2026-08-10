#!/usr/bin/env bash
# Start Phase A API on loopback (docs/00 D7).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT"
export DATA_DIR="${DATA_DIR:-$ROOT/data}"
export OPS_TOKEN="${OPS_TOKEN:-dev-ops-token-change-me}"
# F4 LAN 来源限制（空 = 关闭；非空 = 逗号分隔 CIDR，如 192.168.1.0/24）
export ALLOWED_CIDRS="${ALLOWED_CIDRS:-}"
export LLM_BIG_ENDPOINT="${LLM_BIG_ENDPOINT:-http://127.0.0.1:8001/v1}"
export LLM_BIG_MODEL="${LLM_BIG_MODEL:-qwen3.6-27b}"
export LLM_FAST_ENDPOINT="${LLM_FAST_ENDPOINT:-http://127.0.0.1:8000/v1}"
# Stage 2 transition: Qwen2.5-7B; replace with 9B when weights land (docs/01)
export LLM_FAST_MODEL="${LLM_FAST_MODEL:-qwen2.5-7b}"
export LLM_EMBED_ENDPOINT="${LLM_EMBED_ENDPOINT:-http://127.0.0.1:8002/v1}"
export LLM_EMBED_MODEL="${LLM_EMBED_MODEL:-qwen3-embedding-0.6b}"
export EMBED_FALLBACK_LEXICAL="${EMBED_FALLBACK_LEXICAL:-1}"
export LLM_ENABLE_THINKING="${LLM_ENABLE_THINKING:-0}"
export FRONTEND_DIST="${FRONTEND_DIST:-$ROOT/frontend/dist}"
cd "$ROOT"
exec uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8010}"
