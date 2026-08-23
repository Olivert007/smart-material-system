#!/usr/bin/env bash
# DEPRECATED: use scripts/models.sh start big
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/models.sh" start big
