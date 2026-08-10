#!/usr/bin/env bash
set -euo pipefail
# 默认加载官方 FP8 制品（D4），bf16 27B≈54GB 权重会挤爆 GB10 统一内存；
# FP8 权重由 vLLM 按 config.json 自动识别，无需 --dtype bfloat16（显式 bf16 会强制反量化失去省内存意义）
MODEL_DIR="${MODEL_DIR:-/models/Qwen3.6-27B-FP8}"
PORT="${VLLM_BIG_PORT:-8001}"
NAME="${VLLM_BIG_NAME:-qwen3.6-27b}"
LOG="${VLLM_BIG_LOG:-/tmp/vllm-big-27b.log}"

pkill -f "vllm serve ${MODEL_DIR}" 2>/dev/null || true
sleep 2

nohup vllm serve "$MODEL_DIR" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --gpu-memory-utilization "${GPU_UTIL:-0.45}" \
  --max-model-len "${MAX_LEN:-4096}" \
  --max-num-seqs "${MAX_NUM_SEQS:-16}" \
  --served-model-name "$NAME" \
  --limit-mm-per-prompt '{"image":0}' \
  >"$LOG" 2>&1 &

echo "started pid=$! log=$LOG"
