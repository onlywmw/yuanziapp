#!/bin/bash
# Yuanzi 全量验证脚本
# Usage: bash scripts/verify-all.sh
# 注意：不要用 set -e —— 各阶段用 "cmd; if [ \$? -eq 0 ]" 统计失败，
# set -e 会让首个失败直接退出，fail() 统计沦为死代码（BUG-035）。

PYTHON="${PYTHON:-python}"
PASS=0
FAIL=0
RED='\033[31m'
GREEN='\033[32m'
NC='\033[0m'

# 可移植临时目录（/tmp/yuanzi_*.log 在 Windows 上不可用，BUG-035）
TMPDIR_LOGS=$(mktemp -d 2>/dev/null || mktemp -d -t yuanzi)
trap 'rm -rf "$TMPDIR_LOGS"' EXIT

pass() { echo -e "${GREEN}PASS${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}FAIL${NC} $1 — $2"; FAIL=$((FAIL+1)); }

echo "=========================================="
echo " Yuanzi Full Verification"
echo "=========================================="
echo ""

# ============================================
# Phase 0: 依赖
# ============================================
echo "--- Phase 0: Dependencies ---"

# base-atoms 的非平凡依赖（cryptography>=42 等），干净环境下缺失会导致测试失败
DEP_OK=1
for req in base-atoms/*/requirements.txt; do
    if [ -s "$req" ]; then
        $PYTHON -m pip install -q -r "$req" || DEP_OK=0
    fi
done
if [ "$DEP_OK" -eq 1 ]; then
    pass "Base atom dependencies installed"
else
    fail "Base atom dependencies" "pip install failed"
fi

echo ""

# ============================================
# Phase 1: 代码质量
# ============================================
echo "--- Phase 1: Code Quality ---"

$PYTHON -m pytest yuanzi-cli/tests/ mcp-yuanzi-bridge/tests/ base-atoms/tests/ -q > "$TMPDIR_LOGS/test.log" 2>&1
if [ $? -eq 0 ]; then
    pass "All tests pass"
else
    fail "Tests failed" "$(tail -5 "$TMPDIR_LOGS/test.log")"
fi

$PYTHON -m black --check --config pyproject.toml . > "$TMPDIR_LOGS/black.log" 2>&1
if [ $? -eq 0 ]; then
    pass "Black formatting ok"
else
    fail "Black would reformat" "$(grep 'would reformat' "$TMPDIR_LOGS/black.log" | wc -l) files"
fi

$PYTHON -m ruff check --config pyproject.toml . > "$TMPDIR_LOGS/ruff.log" 2>&1
if [ $? -eq 0 ]; then
    pass "Ruff lint ok"
else
    fail "Ruff errors" "$(grep -c 'E\|F' "$TMPDIR_LOGS/ruff.log") issues"
fi

echo ""

# ============================================
# Phase 2: 原子模型
# ============================================
echo "--- Phase 2: Atom Model ---"

# 基础原子 13 个
BASE_COUNT=$(ls -d base-atoms/*/ 2>/dev/null | grep -v tests | wc -l)
if [ "$BASE_COUNT" -ge 13 ]; then
    pass "Base atoms: $BASE_COUNT (expected >=13)"
else
    fail "Base atoms count" "got $BASE_COUNT, expected >=13"
fi

# 每个基础原子有 core.py 和 server.py
MISSING_FILES=""
for d in base-atoms/*/; do
    name=$(basename "$d")
    [ "$name" = "tests" ] && continue
    [ -f "$d/core.py" ] || MISSING_FILES="$MISSING_FILES $name/core.py"
    [ -f "$d/server.py" ] || MISSING_FILES="$MISSING_FILES $name/server.py"
done
if [ -z "$MISSING_FILES" ]; then
    pass "All base atoms have core.py + server.py"
else
    fail "Missing files" "$MISSING_FILES"
fi

# 旧原子已删除
if [ ! -d "atoms/atom-math-sum" ] && [ ! -d "atoms/atom-file-read" ]; then
    pass "Legacy atoms removed"
else
    fail "Legacy atoms still exist"
fi

# 注册原子有 author
AUTHOR_CHECK=$($PYTHON -c "
import sys; sys.path.insert(0, 'mcp-yuanzi-bridge')
from registry import list_atoms
import sqlite3, os
db = os.environ.get('YUANZI_DB_PATH', '/tmp/test_verify.db')
# Skip if no DB — this is a code check, not runtime
print('skip')
" 2>&1)
echo "  (author check requires agent.db — skip in local)"

echo ""

# ============================================
# Phase 3: Schema 权威源
# ============================================
echo "--- Phase 3: Schema Authority ---"

# registry.py 不应有 CREATE TABLE
# grep -c 无匹配时退出码为 1 且已输出 0，不能再接 || echo 0（会得到 "0\n0"）
DDL_COUNT=$(grep -c "CREATE TABLE" mcp-yuanzi-bridge/registry.py 2>/dev/null || true)
if [ "$DDL_COUNT" -eq 0 ]; then
    pass "registry.py: no CREATE TABLE"
else
    fail "registry.py has $DDL_COUNT CREATE TABLE statements"
fi

# 遗留文件已删除
if [ ! -f "mcp-yuanzi-bridge/insert_atoms.py" ] && [ ! -f "mcp-yuanzi-bridge/import_mcp_servers.py" ]; then
    pass "Legacy scripts removed (insert_atoms, import_mcp_servers)"
else
    fail "Legacy scripts still exist"
fi

# 迁移文件存在
MIG_COUNT=$(ls mcp-yuanzi-bridge/migrations/*.sql 2>/dev/null | wc -l)
if [ "$MIG_COUNT" -ge 8 ]; then
    pass "Migrations: $MIG_COUNT SQL files (expected >=8)"
else
    fail "Migration count" "got $MIG_COUNT, expected >=8"
fi

echo ""

# ============================================
# Phase 4: 接口契约
# ============================================
echo "--- Phase 4: Interface Contracts ---"

$PYTHON -c "
import sys; sys.path.insert(0, 'mcp-yuanzi-bridge')
from registry import (
    submit_atom, review_atom, set_atom_status, get_atom,
    list_atoms, list_atom_versions, get_atom_version,
    rollback_atom, probe_atom, probe_atoms,
    resolve_dependencies, compute_registry_stats,
    dump_registry, get_audit_log
)
print('All 14 contract functions importable')
" 2>&1
if [ $? -eq 0 ]; then
    pass "All 14 contract functions importable"
else
    fail "Contract function import failed"
fi

echo ""

# ============================================
# Phase 5: 文档一致性
# ============================================
echo "--- Phase 5: Documentation ---"

DOC_COUNT=$(ls docs/*.md 2>/dev/null | wc -l)
if [ "$DOC_COUNT" -ge 16 ]; then
    pass "Documentation: $DOC_COUNT files"
else
    fail "Documentation count" "got $DOC_COUNT"
fi

# CLAUDE.md 存在
[ -f CLAUDE.md ] && pass "CLAUDE.md exists" || fail "CLAUDE.md missing"

# README 有项目状态
grep -q "M1" README.md && pass "README has milestone status" || fail "README missing milestones"

echo ""

# ============================================
# Phase 6: 安全
# ============================================
echo "--- Phase 6: Security ---"

# API 认证测试存在
[ -f mcp-yuanzi-bridge/tests/test_auth.py ] && pass "Auth tests exist" || fail "Auth tests missing"

# 审计链测试存在
[ -f mcp-yuanzi-bridge/tests/test_audit_chain.py ] && pass "Audit chain tests exist" || fail "Audit chain tests missing"

# 探针安全测试
grep -q "scheme\|file://\|CIDR\|127.0.0" mcp-yuanzi-bridge/registry.py 2>/dev/null
if [ $? -eq 0 ]; then
    pass "Probe has scheme/CIDR validation"
else
    fail "Probe missing security checks"
fi

echo ""

# ============================================
# 汇总
# ============================================
echo "=========================================="
echo " Results: $PASS passed, $FAIL failed"
echo "=========================================="

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}ALL CHECKS PASSED${NC}"
    exit 0
else
    echo -e "${RED}$FAIL CHECK(S) FAILED${NC}"
    exit 1
fi
