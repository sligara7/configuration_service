#!/usr/bin/env bash
# Launch Configuration Service for demo.
# Usage: bash scripts/demo.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"

export CONFIG_REQUIRE_AUTH=false
export CONFIG_LOAD_STRATEGY=mock
export CONFIG_DB_PATH=/tmp/config_demo.db
export CONFIG_DEVICE_CHANGE_HISTORY_ENABLED=true

echo "Starting Configuration Service (demo mode)"
echo "  Auth:     disabled"
echo "  Strategy: mock"
echo "  DB:       $CONFIG_DB_PATH"
echo "  Swagger:  http://localhost:8004/docs"
echo ""

exec python -m uvicorn configuration_service.main:app \
    --host 0.0.0.0 \
    --port 8004 \
    --reload \
    --reload-dir "$SERVICE_DIR/src"
