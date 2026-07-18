#!/usr/bin/env bash
# Install pre-commit hooks for the Yuanzi repository.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON="python"
fi

echo "Installing pre-commit..."
"$PYTHON" -m pip install pre-commit -q

echo "Installing hooks..."
"$PYTHON" -m pre_commit install --config "${PROJECT_DIR}/.pre-commit-config.yaml"

echo "Hooks installed. They will run automatically on 'git commit'."
echo "To run them manually: pre-commit run --all-files"
