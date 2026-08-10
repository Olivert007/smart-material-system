#!/usr/bin/env bash
# Stage 2 transition: start fast=Qwen2.5-7B on :8000 (docs/01 / 06).
# Requires free GPU headroom alongside big@8001 (util≈0.25) + embed@8002.
# If CUDA OOM, keep Stage1 degraded_up→big; do not force dual-resident.
set -euo pipefail
LOG="${VLLM_FAST_LOG:-/tmp/vllm-fast.log}"
PIDF="${VLLM_FAST_PID:-/tmp/vllm-fast.pid}"
MODEL="${VLLM_FAST_WEIGHTS:-/models/Qwen2.5-7B-Instruct}"
NAME="${LLM_FAST_MODEL:-qwen2.5-7b}"
UTIL="${VLLM_FAST_GPU_UTIL:-0.25}"

if curl -sf --max-time 2 "http://127.0.0.1:8000/v1/models" >/dev/null 2>&1; then
  echo "fast already up on :8000"
  curl -sS --max-time 3 "http://127.0.0.1:8000/v1/models" | head -c 300; echo
  exit 0
fi

if [[ ! -d "$MODEL" ]]; then
  echo "missing weights: $MODEL" >&2
  exit 1
fi

PYTHONUNBUFFERED=1 nohup vllm serve "$MODEL" \
  --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization "$UTIL" \
  --max-model-len 8192 \
  --served-model-name "$NAME" \
  >"$LOG" 2>&1 &
echo $! >"$PIDF"
echo "starting fast pid=$(cat "$PIDF") log=$LOG util=$UTIL"

for i in $(seq 1 120); do
  if curl -sf --max-time 2 "http://127.0.0.1:8000/v1/models" >/dev/null 2>&1; then
    echo "FAST_OK"
    curl -sS --max-time 3 "http://127.0.0.1:8000/v1/models"
    exit 0
  fi
  if ! kill -0 "$(cat "$PIDF")" 2>/dev/null; then
    echo "FAST_FAILED process exited; tail log:" >&2
    tail -n 40 "$LOG" >&2 || true
    exit 2
  fi
  sleep 2
done
echo "FAST_TIMEOUT" >&2
tail -n 40 "$LOG" >&2 || true
exit 3
