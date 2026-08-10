#!/usr/bin/env bash
# Start Stage 1 transitional big model (Qwen2.5-7B on :8001)
set -euo pipefail
MODEL_DIR="${MODEL_DIR:-/models/Qwen2.5-7B-Instruct}"
PORT="${VLLM_BIG_PORT:-8001}"
NAME="${VLLM_BIG_NAME:-qwen2.5-7b}"
LOG="${VLLM_BIG_LOG:-/tmp/vllm-big.log}"

if curl -sf "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
  echo "already up on :${PORT}"
  curl -s "http://127.0.0.1:${PORT}/v1/models"
  exit 0
fi

pkill -f "vllm serve .*--port ${PORT}" 2>/dev/null || true
sleep 1
nohup vllm serve "$MODEL_DIR" \
  --host 0.0.0.0 --port "$PORT" \
  --gpu-memory-utilization "${GPU_UTIL:-0.45}" \
  --max-model-len "${MAX_LEN:-8192}" \
  --served-model-name "$NAME" \
  >"$LOG" 2>&1 &
echo "started pid=$! log=$LOG"
echo "wait with: while ! curl -sf http://127.0.0.1:${PORT}/v1/models; do sleep 5; done"
