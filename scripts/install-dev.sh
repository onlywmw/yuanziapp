#!/usr/bin/env bash
# Install Yuanzi development environment on the local machine.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON="python"
fi

echo "Installing yuanzi-cli in editable mode..."
"$PYTHON" -m pip install -e "${PROJECT_DIR}/yuanzi-cli"

echo ""
echo "Development environment ready."
echo "Try:"
echo "  yuanzi init com.example.my-atom"
echo "  yuanzi validate"
echo "  yuanzi test"
echo ""
echo "To sync to a tablet, ensure adb is connected and run:"
echo "  ${SCRIPT_DIR}/sync-to-device.sh"
