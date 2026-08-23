#!/usr/bin/env bash
# Resolve vllm/vllm-openai image reference with digest for deploy/offline.env (doc 21).
set -euo pipefail

TAG="v0.8.5"
WRITE_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --write)
      WRITE_PATH="${2:?--write requires a path}"
      shift 2
      ;;
    -*)
      echo "unknown option: $1" >&2
      exit 1
      ;;
    *)
      TAG="$1"
      shift
      ;;
  esac
done

IMAGE="vllm/vllm-openai:${TAG}"
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found; set VLLM_IMAGE manually in deploy/offline.env" >&2
  exit 1
fi
docker pull "${IMAGE}"
REF="$(docker inspect --format='{{index .RepoDigests 0}}' "${IMAGE}")"
if [[ -z "${REF}" || "${REF}" != *@sha256:* ]]; then
  echo "failed to resolve digest for ${IMAGE}" >&2
  exit 1
fi
LINE="VLLM_IMAGE=${REF}"

if [[ -n "${WRITE_PATH}" ]]; then
  if [[ ! -f "${WRITE_PATH}" ]]; then
    echo "${WRITE_PATH} not found" >&2
    exit 1
  fi
  if grep -q '^VLLM_IMAGE=' "${WRITE_PATH}"; then
    sed -i "s|^VLLM_IMAGE=.*|${LINE}|" "${WRITE_PATH}"
  else
    printf '\n%s\n' "${LINE}" >> "${WRITE_PATH}"
  fi
  echo "updated ${WRITE_PATH}"
else
  echo "${LINE}"
fi
