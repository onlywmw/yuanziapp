#!/usr/bin/env bash
# Fast pre-commit checks for the example atom.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
EXAMPLE="${PROJECT_DIR}/yuanzi-atom-templates/examples/com.example.sum"

yuanzi validate "$EXAMPLE"
yuanzi test --fast "$EXAMPLE"
