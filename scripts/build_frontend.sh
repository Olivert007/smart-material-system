#!/usr/bin/env bash
# Build Vue dist for F2 FastAPI static hosting (docs/11 §5.1).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
npm run build
echo "Built: $ROOT/frontend/dist"
