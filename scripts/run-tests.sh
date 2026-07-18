#!/bin/bash
# Run all Yuanzi tests.
# Usage: sh scripts/run-tests.sh [-v] [--ci]
#
#   -v     Verbose output
#   --ci   CI mode: exit on first failure
#
# Each test directory runs separately because sub-projects
# (yuanzi-cli) have their own pyproject.toml with pytest config.

set -euo pipefail

PYTHON="${PYTHON:-python3}"
VERBOSE=""
TB="short"
EXIT_FIRST=""

for arg in "$@"; do
    case "$arg" in
        -v) VERBOSE="-v" ;;
        --ci) EXIT_FIRST="-x" ;;
    esac
done

run_tests() {
    local dir="$1"
    echo "  $dir ..."
    $PYTHON -m pytest "$dir" $VERBOSE --tb="$TB" $EXIT_FIRST -q
}

echo "=== Yuanzi tests ==="

SUITES=(
    "yuanzi-cli/tests"
    "mcp-yuanzi-bridge/tests"
    "atoms/tests"
)

PASSED=0
for suite in "${SUITES[@]}"; do
    run_tests "$suite" && ((PASSED++)) || true
done

echo "=== $PASSED/${#SUITES[@]} suites passed ==="
