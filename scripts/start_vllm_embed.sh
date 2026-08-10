#!/usr/bin/env bash
# Start Stage 1 embed model (Qwen3-Embedding-0.6B on :8002)
set -euo pipefail
MODEL_DIR="${MODEL_DIR:-/models/Qwen3-Embedding-0.6B}"
PORT="${VLLM_EMBED_PORT:-8002}"
NAME="${VLLM_EMBED_NAME:-qwen3-embedding-0.6b}"
LOG="${VLLM_EMBED_LOG:-/tmp/vllm-embed.log}"

if curl -sf "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
  echo "already up on :${PORT}"
  curl -s "http://127.0.0.1:${PORT}/v1/models"
  exit 0
fi

pkill -f "vllm serve .*--port ${PORT}" 2>/dev/null || true
sleep 1
nohup vllm serve "$MODEL_DIR" \
  --host 0.0.0.0 --port "$PORT" \
  --runner pooling \
  --convert embed \
  --gpu-memory-utilization "${GPU_UTIL:-0.08}" \
  --max-model-len "${MAX_LEN:-4096}" \
  --served-model-name "$NAME" \
  >"$LOG" 2>&1 &
echo "started pid=$! log=$LOG"
echo "wait with: while ! curl -sf http://127.0.0.1:${PORT}/v1/models; do sleep 3; done"
