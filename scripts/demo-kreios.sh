#!/usr/bin/env bash
# Launch Configuration Service with KREIOS-150 profile collection.
#
# Loads real ophyd devices from the kreios-ioc profile collection.
# The service introspects ophyd Device instances to discover PV names,
# device capabilities, and component structure.
#
# Communication path (when IOC is running):
#   Swagger UI -> Config Service -> ophyd -> EPICS CA -> C++ IOC -> ProdigySimServer
#
# Usage:
#   # Config Service only (no IOC, devices show PVs but won't be connected):
#   bash scripts/demo-kreios.sh
#
#   # Full stack (start simulator + IOC first, then Config Service):
#   bash scripts/demo-kreios.sh --with-ioc
#
# Prerequisites:
#   pip install -e .[dev]   (in services/configuration_service)
#   The kreios-ioc repo at /home/ajs7/project/kreios-ioc
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"
KREIOS_IOC_DIR="/home/ajs7/project/kreios-ioc"
KREIOS_PROFILE="$KREIOS_IOC_DIR/profiles/kreios-profile-collection"

# ── Create a demo profile that skips the broken async device file ──
# (11-devices-async.py has an ophyd_async API mismatch with the
#  installed version; the sync devices in 10-devices.py work fine)
DEMO_PROFILE=$(mktemp -d /tmp/kreios-demo-profile.XXXXXX)
mkdir -p "$DEMO_PROFILE/startup"

for f in "$KREIOS_PROFILE/startup/"*.py; do
    base=$(basename "$f")
    # Skip the async devices file (ophyd_async API incompatibility)
    if [[ "$base" == "11-devices-async.py" ]]; then
        continue
    fi
    ln -sf "$f" "$DEMO_PROFILE/startup/$base"
done

# Copy the YAML catalog too
if [[ -f "$KREIOS_PROFILE/startup/existing_plans_and_devices.yaml" ]]; then
    ln -sf "$KREIOS_PROFILE/startup/existing_plans_and_devices.yaml" \
           "$DEMO_PROFILE/startup/existing_plans_and_devices.yaml"
fi

cleanup() {
    echo ""
    echo "Cleaning up demo profile: $DEMO_PROFILE"
    rm -rf "$DEMO_PROFILE"

    if [[ "${IOC_STARTED:-false}" == "true" ]]; then
        echo "Stopping KREIOS IOC containers..."
        cd "$KREIOS_IOC_DIR/docker" && docker-compose down 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ── Optionally start the full IOC stack ──
if [[ "${1:-}" == "--with-ioc" ]]; then
    echo "=== Starting KREIOS IOC stack ==="
    echo "  Simulator: ProdigySimServer on port 7010"
    echo "  IOC:       KREIOS EPICS IOC (PV prefix KREIOS:cam1:)"
    echo ""

    cd "$KREIOS_IOC_DIR/docker"
    docker-compose up -d simulator
    echo "  Waiting for simulator health check..."
    sleep 5
    docker-compose --profile full up -d
    IOC_STARTED=true
    echo "  IOC started. PVs should be available shortly."
    echo ""

    # Give the IOC a moment to register PVs
    sleep 3

    export EPICS_CA_ADDR_LIST=localhost
    export EPICS_CA_AUTO_ADDR_LIST=NO
    export EPICS_CA_MAX_ARRAY_BYTES=10000000
fi

# ── Configuration Service env vars ──
export CONFIG_REQUIRE_AUTH=false
export CONFIG_LOAD_STRATEGY=startup_scripts
export CONFIG_PROFILE_PATH="$DEMO_PROFILE"
export CONFIG_DB_PATH=/tmp/config_demo_kreios.db
export CONFIG_DEVICE_CHANGE_HISTORY_ENABLED=true

echo "=== Starting Configuration Service (KREIOS profile) ==="
echo "  Auth:     disabled"
echo "  Strategy: startup_scripts"
echo "  Profile:  $KREIOS_PROFILE"
echo "  DB:       $CONFIG_DB_PATH"
echo "  Swagger:  http://localhost:8004/docs"
echo ""
echo "  Devices will be loaded from ophyd introspection."
echo "  Expected: kreios (KreiosDetector), kreios_spectrum, kreios_image"
echo ""

cd "$SERVICE_DIR"
exec python -m uvicorn configuration_service.main:app \
    --host 0.0.0.0 \
    --port 8004 \
    --reload \
    --reload-dir "$SERVICE_DIR/src"
