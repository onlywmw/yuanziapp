#!/usr/bin/env bash
# Install pre-commit hooks for the Yuanzi repository.
# Thin wrapper around `yuanzi install-hooks`; the logic lives in yuanzi-cli.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v yuanzi >/dev/null 2>&1; then
    echo "Error: 'yuanzi' CLI not found. Install it first:" >&2
    echo "  pip install -e ${PROJECT_DIR}/yuanzi-cli" >&2
    exit 1
fi

exec yuanzi install-hooks "${PROJECT_DIR}"
