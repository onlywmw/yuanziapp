#!/usr/bin/env bash
# Run code formatters on the entire Yuanzi repository.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON="python"
fi

echo "Running black..."
"$PYTHON" -m black --config "${PROJECT_DIR}/pyproject.toml" "${PROJECT_DIR}"

echo "Running ruff check --fix..."
"$PYTHON" -m ruff check --config "${PROJECT_DIR}/pyproject.toml" --fix "${PROJECT_DIR}"

echo "Running ruff format..."
"$PYTHON" -m ruff format --config "${PROJECT_DIR}/pyproject.toml" "${PROJECT_DIR}"

echo "Done."
