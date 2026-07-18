# Baseline Metrics - yuanziapp

**Date**: 2026-07-18
**Purpose**: Pre-QA snapshot for comparison during testing
**Repo**: yuanziapp @ main (7205ebe) · Env: Windows 11 / Python 3.12.13

---

## 1. Test Coverage (Current State)

### Unit Tests（仓库自带）
- **Total Tests**: 12（yuanzi-cli 4 + com.example.sum 8）
- **Passing**: 12 (100%)
- **Failing**: 0
- **Coverage**: 未量化（未接入 pytest-cov）

### QA 执行测试（本次）
- **Total Tests**: 63（CLI 20 / Atoms 18 / Registry 15 / Security 10）
- **Passing**: 52 (82.5%)
- **Failing**: 11（对应 13 个缺陷）

### E2E Tests
- **Total Tests**: 0（Android 客户端 widgetmcp_src 未纳入本次执行范围，仅静态审查）

---

## 2. Known Issues (Pre-QA → QA 确认)

### Critical Issues
- [x] BUG-007: atom-file-read 任意文件读取（P0，已确认可利用）
- [x] BUG-008: atom-http-get SSRF（P0，已确认可利用）
- [x] BUG-006: 注册中心能力去重失效（P1，签名含 atom_id）
- [x] BUG-005: 示例原子端口全部 8080 冲突（P1）

### Technical Debt
- [ ] 无 CI（仅本地 pre-commit）
- [ ] 依赖无 lock 文件
- [ ] markdown_rules / prompt_txt 内核类型 validate 通过但 server 未实现
- [ ] 测试相对路径 CWD 脆弱（BUG-004）

---

## 3. Security Status

### OWASP Top 10 Coverage
- [ ] A01: Broken Access Control — ❌ 未缓解（BUG-007 路径穿越）
- [x] A02: Cryptographic Failures — ✅ 无硬编码密钥（token 明文存储/传输已记 BUG-011）
- [x] A03: Injection — ✅ 已缓解（参数化查询，实测注入无效）
- [ ] A04: Insecure Design — ❌ 未缓解（BUG-010 无 body 限制）
- [ ] A05: Security Misconfiguration — ❌ 未缓解（BUG-009 0.0.0.0 无认证、BUG-012 异常泄露）
- [ ] A06: Vulnerable Components — ❌ 未缓解（BUG-013 无锁定/扫描）
- [ ] A07: Authentication Failures — ❌ 未缓解（BUG-009 /run 无鉴权）
- [x] A08: Data Integrity Failures — ✅ 已缓解（yaml.safe_load）
- [x] A09: Logging Failures — ✅ 注册中心审计完整（atoms 无访问日志，建议项）
- [ ] A10: SSRF — ❌ 未缓解（BUG-008）

**Current Coverage**: 4/10 已缓解（40%）· 10/10 已验证（100% 测试覆盖）

---

## 4. Performance Metrics

- 未测量（功能测试阶段，无性能门禁）

---

## 5. Code Quality

- **Linting Errors**: 未运行 pre-commit 全量（black/ruff 配置存在）
- **TypeScript Strict Mode**: N/A（Python/Kotlin 项目）
- **Code Duplication**: atoms/*/server.py 五份近似重复（建议抽公共适配层）
- **Cyclomatic Complexity**: 低（核心模块函数简短）

---

## 6. Predicted Issues → QA 验证结果

**CRITICAL-001**: 示例原子无输入边界防护
- **Predicted Severity**: P0
- **验证结果**: 属实 → BUG-007 / BUG-008
- **Mitigation**: 沙箱 + SSRF 过滤（见 QA-REPORT 修改建议 1-2）

**CRITICAL-002**: 服务对外暴露无认证
- **Predicted Severity**: P1
- **验证结果**: 属实 → BUG-009
- **Mitigation**: 默认 127.0.0.1 + 可选 token（见 QA-REPORT 修改建议 3）

---

**Next Steps**: 修复 P0×2 → 复跑 TC-SEC-001/002 → 质量门禁达标后进入 M2。
