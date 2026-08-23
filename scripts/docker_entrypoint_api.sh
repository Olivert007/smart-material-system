#!/usr/bin/env bash
# Docker entrypoint: seed data volume then start API (doc 21).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${PYTHONPATH:-$ROOT}"
export DATA_DIR="${DATA_DIR:-/app/data}"
export SEED_DIR="${SEED_DIR:-/app/seed}"
python3 "$ROOT/scripts/init_data_volume.py"
exec "$@"
