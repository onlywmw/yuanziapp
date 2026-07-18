# Yuanzi Bug 注册表

> 来源: Audit #1 (689ad4e) + Audit #2 (689ad4e..1a61a86)
> 更新: 2026-07-18

---

## P0 — 安全漏洞（必须立即修复）

| BUG | 描述 | 攻击向量 | 状态 |
|-----|------|----------|------|
| BUG-025 | REST API 14 路由零认证，含 5 个写路由。任何可达端口的调用方可自审自批、改状态、回滚 | OWASP A01: Broken Access Control | Open |
| BUG-020 | probe 对注册表中的任意 URL 发起真实 HTTP 请求，无 scheme/地址校验。不可信注册数据 = 内网扫描器 | SSRF + 内网探测 | Open |
| BUG-007 | atom-file-read 无路径校验，可读取任意文件 | 任意文件读取 | Open |
| BUG-008 | atom-http-get 无 URL 校验，可请求内网地址 | SSRF | Open |

---

## P1 — 致命逻辑错误（阻塞合并）

| BUG | 文件 | 症状 | 状态 |
|-----|------|------|------|
| BUG-014 | registry.py | `probe_atom` 遇 `file://` scheme 崩溃（TypeError: '<=' not supported between 'int' and 'NoneType'）。`probe_atoms` 批量循环无隔离，一行坏数据中断整个批量 | Open |
| BUG-016 | registry.py | `content_hash` 只写内存不落库。同能力不同 atom_id 仍注册成功。能力去重形同虚设 | Open |
| BUG-023 | 多文件 | Schema/契约漂移：`003_atom_versions.sql` 无 `changelog` 列 → `OperationalError`。`resolve_dependencies` 契约键名变更 → 6 个测试 KeyError。`migrations/__init__.py` 重写破坏框架契约 | Open |
| BUG-024 | registry.py | `1a61a86` 将 `probe_atom` 回退为功能桩：不更新 lifecycle、不写 runtime_json 探测字段、不写审计、无 `success` 键 → 9 个测试失败 | Open |
| BUG-015 | yuanzi-cli | `install-hooks` 的 `_find_repo_root` 向上搜索无边界。负路径测试未 stub subprocess → 在祖先含 `.pre-commit-config.yaml` 的机器上真实执行 pip install | Open |

---

## P2 — 规范/质量问题（需排期）

| BUG | 描述 |
|-----|------|
| BUG-017 | `probing` 状态为死代码——无任何路径设置该状态，与状态机声明不符 |
| BUG-018 | probe 的 `not_found`/`no_endpoint` 分支不写审计，与提交说明矛盾 |
| BUG-019 | probe 绕过 `set_atom_status` 状态机：实测发生流转表不允许的 `offline→unreachable` |
| BUG-021 | probe CLI 恒 exit 0、串行执行、`--json` 无汇总，无法用于监控告警 |
| BUG-022 | 每次探测写一条审计，定时探测将刷爆审计表 |
| BUG-026 | `ensure_registry_schema` 公共契约静默改变——调用方不知道 Schema 已变 |
| BUG-027 | `probe_atoms` 签名变更未同步 CLI |

---

## 统计

| 级别 | 数量 | 
|------|------|
| P0 安全 | 4 |
| P1 阻塞 | 5 |
| P2 规范 | 7 |
| **总计** | **16** |

## 30 个测试失败分布

| 测试文件 | 失败数 | 关联 BUG |
|----------|--------|----------|
| test_versions | 5 | BUG-023 |
| test_dependencies | 6 | BUG-023 |
| test_probe | 9 | BUG-024 |
| test_migrations | 6 | BUG-023 |
| test_api | 3 | BUG-023 |
| test_validate_schema | 1 | BUG-026 |
