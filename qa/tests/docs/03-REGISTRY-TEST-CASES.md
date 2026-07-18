# 03 - mcp-yuanzi-bridge 注册中心 测试用例（权威来源）

**组件**：`mcp-yuanzi-bridge/registry.py`（sqlite 注册中心：提交/审核/状态流转/查询/审计）
**执行方式**：Python 直接调用，使用临时目录下的 sqlite 数据库；`conn.row_factory = sqlite3.Row`

---

## TC-REG-001 提交新原子 [P0]

- **准备**：内存/临时 DB，`ensure_registry_schema`；构造最小合法 atom（atom_id/name/purpose/architecture/ownership）
- **执行**：`submit_atom(conn, atom, actor="qa")`
- **断言**：`success == True`；status == "submitted"；返回 32 位 signature

## TC-REG-002 重复 signature 被不同 atom_id 占用 [P0]

- **准备**：已注册 atom A（同 functions/type/runtime/interface/deps）
- **执行**：用相同能力但不同 atom_id 的 atom B 再 `submit_atom`
- **断言**：`success == False`，error == `duplicate_signature`

## TC-REG-003 同 atom_id 重复提交 → 更新 [P1]

- **准备**：已提交 atom A
- **执行**：修改 description 后再次 `submit_atom`（同 atom_id）
- **断言**：success；`get_atom` 读到新 description；审计日志有 2 条 submit

## TC-REG-004 审核通过 → registered [P0]

- **准备**：已提交 atom
- **执行**：`review_atom(conn, id, approved=True, reviewer="qa", score=9)`
- **断言**：status == "registered"；review_score == 9；审计记录 review

## TC-REG-005 审核拒绝 → rejected [P1]

- **执行**：`review_atom(..., approved=False, comments="bad")`
- **断言**：status == "rejected"

## TC-REG-006 审核不存在的原子 [P1]

- **执行**：`review_atom(conn, "com.ghost.x", True)`
- **断言**：`success == False`，error == `not_found`

## TC-REG-007 合法状态流转 registered→running [P0]

- **准备**：registered 原子
- **执行**：`set_atom_status(conn, id, "running")`
- **断言**：success，new_status == "running"

## TC-REG-008 非法状态流转 submitted→running [P1]

- **准备**：submitted（未审核）原子
- **执行**：`set_atom_status(conn, id, "running")`
- **断言**：`success == False`，error == `invalid_transition`

## TC-REG-009 list_atoms 按 status 过滤 [P1]

- **准备**：3 个原子（submitted / registered / running 各一）
- **执行**：`list_atoms(conn, status="running")`
- **断言**：只返回 running 那个

## TC-REG-010 list_atoms 搜索 [P2]

- **执行**：`list_atoms(conn, search="关键词")`
- **断言**：命中 atom_id/name/alias 的原子被返回

## TC-REG-011 审计日志完整性 [P1]

- **准备**：完成 提交→审核→状态变更
- **执行**：`get_audit_log(conn, atom_id)`
- **断言**：至少 3 条记录（submit/review/status_change），old/new status 正确

## TC-REG-012 search 参数 SQL 注入尝试 [P0 安全]

- **执行**：`list_atoms(conn, search="' OR '1'='1")`
- **断言**：不返回全表（参数化查询生效），无异常

## TC-REG-013 submit 缺 atom_id [P1]

- **执行**：`submit_atom(conn, {"name": "x"})`
- **断言**：抛 `ValueError("atom_id is required")`

## TC-REG-014 rejected 原子重新提交的状态流转 [P2]

- **准备**：rejected 原子
- **执行**：再次 `submit_atom`
- **断言**：status 回到 submitted（记录实际行为，评估是否符合预期工作流）

## TC-REG-015 deprecated→registered 回滚 [P2]

- **准备**：registered→deprecated
- **执行**：`set_atom_status(..., "registered")`
- **断言**：success（allowed_transitions 允许）
