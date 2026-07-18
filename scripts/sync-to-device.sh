#!/usr/bin/env bash
# Sync Yuanzi project files to the Android tablet via adb.
# This wrapper just calls the Python implementation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON="python"
fi

exec "$PYTHON" "${SCRIPT_DIR}/sync-to-device.py" --config "${PROJECT_DIR}/yuanzi-config.yaml" "$@"
