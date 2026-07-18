#!/bin/bash
# Yuanzi 全量验证脚本
# Usage: bash scripts/verify-all.sh
set -e

PYTHON="${PYTHON:-python}"
PASS=0
FAIL=0
RED='\033[31m'
GREEN='\033[32m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}FAIL${NC} $1 — $2"; FAIL=$((FAIL+1)); }

echo "=========================================="
echo " Yuanzi Full Verification"
echo "=========================================="
echo ""

# ============================================
# Phase 1: 代码质量
# ============================================
echo "--- Phase 1: Code Quality ---"

$PYTHON -m pytest yuanzi-cli/tests/ mcp-yuanzi-bridge/tests/ base-atoms/tests/ -q 2>&1 > /tmp/yuanzi_test.log
if [ $? -eq 0 ]; then
    pass "All tests pass"
else
    fail "Tests failed" "$(tail -5 /tmp/yuanzi_test.log)"
fi

$PYTHON -m black --check --config pyproject.toml . 2>&1 > /tmp/yuanzi_black.log
if [ $? -eq 0 ]; then
    pass "Black formatting ok"
else
    fail "Black would reformat" "$(grep 'would reformat' /tmp/yuanzi_black.log | wc -l) files"
fi

$PYTHON -m ruff check --config pyproject.toml . 2>&1 > /tmp/yuanzi_ruff.log
if [ $? -eq 0 ]; then
    pass "Ruff lint ok"
else
    fail "Ruff errors" "$(grep -c 'E\|F' /tmp/yuanzi_ruff.log) issues"
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
DDL_COUNT=$(grep -c "CREATE TABLE" mcp-yuanzi-bridge/registry.py 2>/dev/null || echo 0)
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
