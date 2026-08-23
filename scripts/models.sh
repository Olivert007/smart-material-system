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

BIG_DIR="${MODEL_DIR_BIG:-${MODEL_DIR:-/models/Qwen3.6-27B-FP8}}"
BIG_NAME="${VLLM_BIG_MODEL:-${LLM_BIG_MODEL:-qwen3.6-27b}}"
FAST_DIR="${MODEL_DIR_FAST:-/models/Qwen2.5-7B-Instruct}"
FAST_NAME="${VLLM_FAST_MODEL:-${LLM_FAST_MODEL:-qwen2.5-7b}}"
EMBED_DIR="${MODEL_DIR_EMBED:-/models/Qwen3-Embedding-0.6B}"
EMBED_NAME="${VLLM_EMBED_MODEL:-${LLM_EMBED_MODEL:-qwen3-embedding-0.6b}}"

# 看门狗/本脚本可用的内存余量下限（GB）：fast/embed 驻留前检查
FAST_MIN_FREE_GB="${FAST_MIN_FREE_GB:-30}"
EMBED_MIN_FREE_GB="${EMBED_MIN_FREE_GB:-8}"

# M-3：embed 推理设备 gpu（vLLM GPU，默认）| cpu（内存紧张时迁移，vLLM --device cpu）
EMBED_DEVICE="${EMBED_DEVICE:-gpu}"
# mem-guard 阈值（02 §7.2）：available 低于阈值按 embed→fast 顺序停，不停 big
GUARD_EMBED_GB="${GUARD_EMBED_GB:-15}"
GUARD_FAST_GB="${GUARD_FAST_GB:-10}"

is_up() { curl -sf --max-time 2 "http://127.0.0.1:$1/v1/models" >/dev/null 2>&1; }

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -q ":${port} "
    return $?
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$port" >/dev/null 2>&1
    return $?
  fi
  curl -sf --max-time 1 "http://127.0.0.1:${port}/" >/dev/null 2>&1
}

role_port() {
  case "$1" in
    big) echo "$BIG_PORT";;
    fast) echo "$FAST_PORT";;
    embed) echo "$EMBED_PORT";;
    *) return 1;;
  esac
}

role_model_name() {
  case "$1" in
    big) echo "$BIG_NAME";;
    fast) echo "$FAST_NAME";;
    embed) echo "$EMBED_NAME";;
    *) return 1;;
  esac
}

role_pid_file() {
  echo "/tmp/vllm-$1.pid"
}

pid_cmdline() {
  local pid="$1"
  tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null || true
}

ensure_port_free() {
  local name="$1" port
  port="$(role_port "$name")"
  if is_up "$port"; then
    return 0
  fi
  if port_in_use "$port"; then
    echo "port :$port in use but $name /v1/models not ready" >&2
    return 1
  fi
  return 0
}

stop_pid() {
  local pid="$1" name="$2"
  if ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi
  kill -TERM "$pid" 2>/dev/null || true
  local i
  for ((i = 0; i < 10; i++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "stopped $name pid=$pid"
      return 0
    fi
    sleep 1
  done
  kill -KILL "$pid" 2>/dev/null || true
  echo "FORCE_KILL: $name pid=$pid" >&2
}

wait_ready() {
  local name="$1" port timeout
  case "$name" in
    fast) timeout="${WAIT_FAST_SEC:-30}"; port="$FAST_PORT";;
    embed) timeout="${WAIT_EMBED_SEC:-180}"; port="$EMBED_PORT";;
    big) timeout="${WAIT_BIG_SEC:-1200}"; port="$BIG_PORT";;
    *) echo "wait_ready: unknown role $name" >&2; return 1;;
  esac
  local start_ts=$SECONDS
  while (( SECONDS - start_ts < timeout )); do
    if is_up "$port"; then
      echo "$name ready on :$port"
      return 0
    fi
    sleep 2
  done
  echo "$name wait_ready timeout after ${timeout}s (see /tmp/vllm-${name}.log)" >&2
  return 1
}

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
  local name="$1" port
  port="$(role_port "$name")"
  curl -sf --max-time 2 "http://127.0.0.1:${port}/v1/models" 2>/dev/null | head -c 200 || true
  ensure_port_free "$name" || return 1
  case "$name" in
    big)
      local log=/tmp/vllm-big.log pid
      pid="$(role_pid_file big)"
      if is_up "$BIG_PORT"; then echo "big already up on :$BIG_PORT"; return 0; fi
      [[ -d "$BIG_DIR" ]] || { echo "missing weights: $BIG_DIR" >&2; return 1; }
      nohup vllm serve "$BIG_DIR" --host 0.0.0.0 --port "$BIG_PORT" \
        --gpu-memory-utilization "${GPU_UTIL_BIG:-0.45}" --max-model-len "${MAX_LEN_BIG:-4096}" \
        --max-num-seqs "${MAX_NUM_SEQS:-16}" --served-model-name "$BIG_NAME" \
        --limit-mm-per-prompt '{"image":0}' >"$log" 2>&1 &
      echo $! >"$pid"
      echo "big starting pid=$(cat "$pid") log=$log model=$BIG_NAME"
      wait_ready big;;
    fast)
      local log=/tmp/vllm-fast.log pid
      pid="$(role_pid_file fast)"
      if is_up "$FAST_PORT"; then echo "fast already up on :$FAST_PORT"; return 0; fi
      [[ -d "$FAST_DIR" ]] || { echo "missing weights: $FAST_DIR" >&2; return 1; }
      if (( $(free_gb) < FAST_MIN_FREE_GB )); then
        echo "SKIP_FAST_OOM: mem_free=$(free_gb)GB < ${FAST_MIN_FREE_GB}GB" >&2
        return 0
      fi
      nohup vllm serve "$FAST_DIR" --host 0.0.0.0 --port "$FAST_PORT" \
        --gpu-memory-utilization "${GPU_UTIL_FAST:-0.25}" --max-model-len "${MAX_LEN_FAST:-8192}" \
        --served-model-name "$FAST_NAME" >"$log" 2>&1 &
      echo $! >"$pid"
      echo "fast starting pid=$(cat "$pid") log=$log model=$FAST_NAME"
      wait_ready fast;;
    embed)
      local log=/tmp/vllm-embed.log pid device_args=()
      pid="$(role_pid_file embed)"
      if is_up "$EMBED_PORT"; then echo "embed already up on :$EMBED_PORT"; return 0; fi
      [[ -d "$EMBED_DIR" ]] || { echo "missing weights: $EMBED_DIR" >&2; return 1; }
      if [[ "$EMBED_DEVICE" == "cpu" ]]; then
        device_args+=(--device cpu)
      else
        if (( $(free_gb) < EMBED_MIN_FREE_GB )); then
          echo "SKIP_EMBED_OOM: mem_free=$(free_gb)GB < ${EMBED_MIN_FREE_GB}GB" >&2
          return 0
        fi
        device_args+=(--gpu-memory-utilization "${GPU_UTIL_EMBED:-0.08}")
      fi
      nohup vllm serve "$EMBED_DIR" --host 0.0.0.0 --port "$EMBED_PORT" \
        --runner pooling --convert embed --max-model-len "${MAX_LEN_EMBED:-4096}" \
        --served-model-name "$EMBED_NAME" "${device_args[@]}" \
        >"$log" 2>&1 &
      echo $! >"$pid"
      echo "embed starting pid=$(cat "$pid") log=$log device=$EMBED_DEVICE model=$EMBED_NAME"
      wait_ready embed;;
    *) echo "unknown endpoint: $name" >&2; return 1;;
  esac
}

stop_one() {
  local name="$1" port model pidfile pid cmd found=0
  port="$(role_port "$name")"
  model="$(role_model_name "$name")"
  pidfile="$(role_pid_file "$name")"
  if [[ -f "$pidfile" ]]; then
    pid="$(tr -d '[:space:]' <"$pidfile")"
    if [[ -n "$pid" ]]; then
      cmd="$(pid_cmdline "$pid")"
      if [[ "$cmd" == *vllm* && "$cmd" == *"$model"* ]]; then
        stop_pid "$pid" "$name" && found=1
      fi
    fi
    rm -f "$pidfile"
  fi
  for entry in /proc/[0-9]*; do
    [[ -e "$entry" ]] || continue
    pid="${entry#/proc/}"
    cmd="$(pid_cmdline "$pid")"
    if [[ "$cmd" == *vllm* && "$cmd" == *"--port ${port}"* ]]; then
      stop_pid "$pid" "$name" && found=1
    fi
  done
  if (( found )); then
    return 0
  fi
  echo "$name :$port not running"
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
      all)
        degraded=0
        if ! start_one big; then
          degraded=1
          if [[ "${ALLOW_DEGRADED_START:-0}" != "1" ]]; then
            echo "big start failed; set ALLOW_DEGRADED_START=1 to continue fast/embed" >&2
            exit 1
          fi
        fi
        start_one embed || true
        start_one fast || true
        if (( degraded )); then echo "DEGRADED_START: big unavailable"; fi
        ;;
      big|fast|embed) start_one "$2";;
      *) echo "usage: models.sh start <big|fast|embed|all>" >&2; exit 1;;
    esac;;
  wait)
    case "${2:-}" in
      big|fast|embed) wait_ready "$2";;
      *) echo "usage: models.sh wait <big|fast|embed>" >&2; exit 1;;
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
