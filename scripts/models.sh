#!/usr/bin/env bash
# 按需起停 vLLM 模型端点（docs/01）：big=:8001(27B-FP8) fast=:8000(7B) embed=:8002(0.6B)
# 用法:
#   scripts/models.sh status                # 查看各端点与进程
#   scripts/models.sh start big             # 启动指定端点（幂等）
#   scripts/models.sh start all             # 启动全部（fast 仅在内存余量足够时）
#   scripts/models.sh stop big              # 停止指定端点
#   scripts/models.sh stop all              # 停止全部
#   EMBED_DEVICE=cpu scripts/models.sh start embed   # embed 迁 CPU（M-3）
#   scripts/models.sh mem-guard                      # 内存看门狗：available 低于阈值停 embed→fast，不停 big
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

BIG_PORT="${VLLM_BIG_PORT:-8001}"
FAST_PORT="${VLLM_FAST_PORT:-8000}"
EMBED_PORT="${VLLM_EMBED_PORT:-8002}"

BIG_DIR="${MODEL_DIR_BIG:-/models/Qwen3.6-27B-FP8}"
BIG_NAME="${LLM_BIG_MODEL:-qwen3.6-27b}"
FAST_DIR="${MODEL_DIR_FAST:-/models/Qwen2.5-7B-Instruct}"
FAST_NAME="${LLM_FAST_MODEL:-qwen2.5-7b}"
EMBED_DIR="${MODEL_DIR_EMBED:-/models/Qwen3-Embedding-0.6B}"
EMBED_NAME="${LLM_EMBED_MODEL:-qwen3-embedding-0.6b}"

# 看门狗/本脚本可用的内存余量下限（GB）：fast/embed 驻留前检查
FAST_MIN_FREE_GB="${FAST_MIN_FREE_GB:-30}"
EMBED_MIN_FREE_GB="${EMBED_MIN_FREE_GB:-8}"

# M-3：embed 推理设备 gpu（vLLM GPU，默认）| cpu（内存紧张时迁移，vLLM --device cpu）
EMBED_DEVICE="${EMBED_DEVICE:-gpu}"
# mem-guard 阈值（02 §7.2）：available 低于阈值按 embed→fast 顺序停，不停 big
GUARD_EMBED_GB="${GUARD_EMBED_GB:-15}"
GUARD_FAST_GB="${GUARD_FAST_GB:-10}"

is_up() { curl -sf --max-time 2 "http://127.0.0.1:$1/v1/models" >/dev/null 2>&1; }

free_gb() {
  # GB10 统一内存：取 MemAvailable（KB）→ GB
  awk '/MemAvailable/{printf "%d", $2/1024/1024}' /proc/meminfo
}

status() {
  local pair name port
  for pair in "big:$BIG_PORT" "fast:$FAST_PORT" "embed:$EMBED_PORT"; do
    name="${pair%%:*}"; port="${pair##*:}"
    if is_up "$port"; then
      local model
      model="$(curl -sf --max-time 3 "http://127.0.0.1:$port/v1/models" | grep -o '"id":"[^"]*"' | head -1)"
      echo "OK   $name :$port $model"
    else
      echo "DOWN $name :$port"
    fi
  done
  echo "mem_free=$(free_gb)GB"
}

start_one() {
  local name="$1"
  case "$name" in
    big)
      local log=/tmp/vllm-big-27b.log pid=/tmp/vllm-big-27b.pid
      if is_up "$BIG_PORT"; then echo "big already up on :$BIG_PORT"; return 0; fi
      [[ -d "$BIG_DIR" ]] || { echo "missing weights: $BIG_DIR" >&2; return 1; }
      nohup vllm serve "$BIG_DIR" --host 0.0.0.0 --port "$BIG_PORT" \
        --gpu-memory-utilization "${GPU_UTIL_BIG:-0.45}" --max-model-len "${MAX_LEN_BIG:-4096}" \
        --max-num-seqs "${MAX_NUM_SEQS:-16}" --served-model-name "$BIG_NAME" \
        --limit-mm-per-prompt '{"image":0}' >"$log" 2>&1 &
      echo $! >"$pid"
      echo "big starting pid=$(cat "$pid") log=$log";;
    fast)
      local log=/tmp/vllm-fast.log pid=/tmp/vllm-fast.pid
      if is_up "$FAST_PORT"; then echo "fast already up on :$FAST_PORT"; return 0; fi
      [[ -d "$FAST_DIR" ]] || { echo "missing weights: $FAST_DIR" >&2; return 1; }
      if (( $(free_gb) < FAST_MIN_FREE_GB )); then
        echo "skip fast: mem_free=$(free_gb)GB < ${FAST_MIN_FREE_GB}GB (防 OOM)" >&2; return 1
      fi
      nohup vllm serve "$FAST_DIR" --host 0.0.0.0 --port "$FAST_PORT" \
        --gpu-memory-utilization "${GPU_UTIL_FAST:-0.25}" --max-model-len "${MAX_LEN_FAST:-8192}" \
        --served-model-name "$FAST_NAME" >"$log" 2>&1 &
      echo $! >"$pid"
      echo "fast starting pid=$(cat "$pid") log=$log";;
    embed)
      local log=/tmp/vllm-embed.log pid=/tmp/vllm-embed.pid device_args=()
      if is_up "$EMBED_PORT"; then echo "embed already up on :$EMBED_PORT"; return 0; fi
      [[ -d "$EMBED_DIR" ]] || { echo "missing weights: $EMBED_DIR" >&2; return 1; }
      if [[ "$EMBED_DEVICE" == "cpu" ]]; then
        # M-3 CPU 模式：vLLM --device cpu，不占用 GPU 显存；仅需系统内存
        device_args+=(--device cpu)
      else
        if (( $(free_gb) < EMBED_MIN_FREE_GB )); then
          echo "skip embed: mem_free=$(free_gb)GB < ${EMBED_MIN_FREE_GB}GB (防 OOM)" >&2; return 1
        fi
        device_args+=(--gpu-memory-utilization "${GPU_UTIL_EMBED:-0.08}")
      fi
      nohup vllm serve "$EMBED_DIR" --host 0.0.0.0 --port "$EMBED_PORT" \
        --runner pooling --convert embed --max-model-len "${MAX_LEN_EMBED:-4096}" \
        --served-model-name "$EMBED_NAME" "${device_args[@]}" \
        >"$log" 2>&1 &
      echo $! >"$pid"
      echo "embed starting pid=$(cat "$pid") log=$log device=$EMBED_DEVICE";;
    *) echo "unknown endpoint: $name" >&2; return 1;;
  esac
}

stop_one() {
  local name="$1" port
  case "$name" in
    big) port="$BIG_PORT";;
    fast) port="$FAST_PORT";;
    embed) port="$EMBED_PORT";;
    *) echo "unknown endpoint: $name" >&2; return 1;;
  esac
  pkill -f "vllm serve .*--port ${port}" 2>/dev/null && echo "stopped $name :$port" || echo "$name :$port not running"
}

mem_guard() {
  # 02 §7.2：available 低于阈值按优先级停 embed → fast；不停 big（交互主路径）。
  # 日志写 data/eval/mem_guard_*.json（看门狗/巡检可回溯）。
  local avail after ts log actions=()
  avail="$(free_gb)"
  ts="$(date +%Y%m%dT%H%M%S)"
  mkdir -p "$ROOT/data/eval"
  log="$ROOT/data/eval/mem_guard_${ts}.json"
  if (( avail < GUARD_EMBED_GB )); then
    actions+=("stop embed (avail=${avail}GB < ${GUARD_EMBED_GB}GB)")
    stop_one embed
  fi
  after="$(free_gb)"
  if (( after < GUARD_FAST_GB )); then
    actions+=("stop fast (avail=${after}GB < ${GUARD_FAST_GB}GB)")
    stop_one fast
  fi
  after="$(free_gb)"
  python3 - "$log" "$avail" "$after" "$(IFS='; '; echo "${actions[*]:-none}")" <<'PY'
import json, sys, time
log, avail, after, actions = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
with open(log, "w") as f:
    json.dump(
        {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "mem_available_gb": avail,
         "mem_after_gb": after, "actions": actions, "big_kept": True},
        f, ensure_ascii=False,
    )
PY
  if (( ${#actions[@]} > 0 )); then
    echo "mem-guard: $(IFS='; '; echo "${actions[*]}") now avail=${after}GB log=$log"
  else
    echo "mem-guard: ok avail=${avail}GB (guard embed=${GUARD_EMBED_GB}GB fast=${GUARD_FAST_GB}GB)"
  fi
}

case "${1:-status}" in
  status) status;;
  start)
    case "${2:-}" in
      all) start_one big; start_one embed; start_one fast;;
      big|fast|embed) start_one "$2";;
      *) echo "usage: models.sh start <big|fast|embed|all>" >&2; exit 1;;
    esac;;
  stop)
    case "${2:-}" in
      all) stop_one big; stop_one fast; stop_one embed;;
      big|fast|embed) stop_one "$2";;
      *) echo "usage: models.sh stop <big|fast|embed|all>" >&2; exit 1;;
    esac;;
  mem-guard) mem_guard;;
  *) echo "usage: models.sh <status|start|stop|mem-guard> [big|fast|embed|all]" >&2; exit 1;;
esac
