# BUG-025 验收标准（Acceptance Criteria）

> **制定者**: Audit · **日期**: 2026-07-18
> **基准文档**: `docs/DESIGN_M6_SECURITY.md`（Arch，design-ready @ 4a7a903）
> **缺陷**: BUG-025（P1）— `mcp-yuanzi-bridge/api.py` 14 条路由零鉴权，含 5 个写路由（自审自批通道）
> **OWASP 映射**: A01 访问控制缺陷 / A07 认证失败 / A09 安全日志记录
> **关闭条件**: 全部 P0 检查点 Pass 且 P1 ≤ 1 项挂起（须记录原因），经 Audit 第三轮复检实证。

---

## 检查点总表

| # | 检查点 | 对应 M6 子任务 | 严重度 | 状态 |
|---|--------|---------------|--------|------|
| AC-01 | 无 token 请求受保护路由 → 401 | M6.1a | P0 | ⬜ Pending |
| AC-02 | 错误 token → 401，常量时间比较 | M6.1a | P0 | ⬜ Pending |
| AC-03 | 有效 token 读路由 → 200 | M6.1a | P0 | ⬜ Pending |
| AC-04 | 开发模式退化有警告日志 | M6.1a | P1 | ⬜ Pending |
| AC-05 | token 来源优先级 env > registry_meta | M6.1a | P1 | ⬜ Pending |
| AC-06 | `api_tokens` 表迁移字段齐全 | M6.1b | P0 | ⬜ Pending |
| AC-07 | token 管理端点仅 admin 可用 | M6.1b | P0 | ⬜ Pending |
| AC-08 | token 仅存 SHA-256 哈希，明文仅创建时返回一次 | M6.1b | P0 | ⬜ Pending |
| AC-09 | 吊销 token 立即失效 → 401 | M6.1b | P1 | ⬜ Pending |
| AC-10 | 过期 token → 401 | M6.1b | P1 | ⬜ Pending |
| AC-11 | RBAC 四角色路由权限矩阵逐项验证 | M6.2a/2b | P0 | ⬜ Pending |
| AC-12 | 14 条路由全部绑定 `require_role`，零遗漏 | M6.2b | P0 | ⬜ Pending |
| AC-13 | 401/403 事件写入审计日志 | M6.2a | P1 | ⬜ Pending |
| AC-14 | 回归：全量套件在有效 token 下通过 | 全部 | P0 | ⬜ Pending |

---

## 逐项验证方法（AAA）

### AC-01 无 token 拒绝（P0）

- **准备**: 设置 `YUANZI_API_TOKEN=test-secret`，启动 API 服务
- **执行**: `curl -i http://127.0.0.1:8081/api/v1/atoms`（不带 Authorization 头）
- **断言**: HTTP 401，响应体含 `Missing Bearer token`；对 14 条路由逐一重复，全部 401

### AC-02 错误 token 拒绝（P0）

- **准备**: 同上
- **执行**: `curl -i -H "Authorization: Bearer wrong-token" http://127.0.0.1:8081/api/v1/atoms`
- **断言**: HTTP 401；代码审查确认使用 `secrets.compare_digest` 比较（禁止 `==`，防时序侧信道）

### AC-03 有效 token 放行（P0）

- **准备**: 有效 admin token
- **执行**: `curl -i -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8081/api/v1/atoms`
- **断言**: HTTP 200，返回正常业务数据

### AC-04 开发模式退化（P1）

- **准备**: 清空 `YUANZI_API_TOKEN` 且 `registry_meta` 无 `api_token`
- **执行**: 启动服务并请求任一路由
- **断言**: 请求放行，但日志出现明确的"开发模式/未配置 token"警告；生产部署文档中注明此模式禁用

### AC-05 token 来源优先级（P1）

- **准备**: env 与 `registry_meta` 各设一个不同 token
- **执行**: 分别用两个 token 请求
- **断言**: 仅 env token 通过；移除 env 后 `registry_meta` token 生效

### AC-06 api_tokens 表结构（P0）

- **准备**: 执行迁移
- **执行**: `PRAGMA table_info(api_tokens)` + 插入重复 token_hash
- **断言**: 字段含 `token_hash`(UNIQUE)/`role`/`created_at`/`expires_at`/`revoked_at`；重复 hash 触发唯一约束错误

### AC-07 token 管理端点鉴权（P0）

- **准备**: admin / registry / viewer / probe 四种 token 各一
- **执行**: 四种 token 分别调用 `POST /api/v1/tokens`、`GET /api/v1/tokens`、`DELETE /api/v1/tokens/{id}`
- **断言**: 仅 admin → 2xx；其余三种 → 403

### AC-08 token 哈希存储（P0）

- **准备**: admin token 创建一个新 token
- **执行**: `SELECT token_hash FROM api_tokens` 对比明文
- **断言**: 库中值为 SHA-256(明文)，无明文列；创建端点响应含完整 token 且后续 `GET /api/v1/tokens` 不再返回完整值

### AC-09 吊销生效（P1）

- **准备**: 创建 token 并验证可用
- **执行**: `DELETE /api/v1/tokens/{id}` 后立即用该 token 请求
- **断言**: 401；`revoked_at` 已写入

### AC-10 过期生效（P1）

- **准备**: 创建 `expires_at` 为过去时间的 token
- **执行**: 用该 token 请求
- **断言**: 401

### AC-11 RBAC 权限矩阵（P0）

按设计 §3.2 路由权限映射逐项验证：

| token 角色 | GET /atoms | POST /atoms | POST /{id}/status | POST /{id}/review | POST /{id}/rollback | POST /{id}/probe | POST /search |
|---|---|---|---|---|---|---|---|
| admin | 200 | 2xx | 2xx | 2xx | 2xx | 2xx | 2xx |
| registry | 200 | 2xx | 2xx | **403** | **403** | — | 2xx |
| viewer | 200 | **403** | **403** | **403** | **403** | **403** | 2xx |
| probe | 200 | **403** | **403** | **403** | **403** | 2xx | — |

- **断言**: 每个单元格实测与矩阵一致（重点：viewer 对 5 个写路由全 403 = 自审自批通道关闭的直接证据）

### AC-12 路由绑定零遗漏（P0）

- **执行**: `grep -n "require_role\|Depends" mcp-yuanzi-bridge/api.py`，对照路由清单逐条核对
- **断言**: 14 条业务路由全部绑定角色依赖（`/health` 等明确豁免项须在设计中列明）；附 grep 输出为证

### AC-13 安全事件审计（P1）

- **准备**: 触发一次 401（无 token）与一次 403（viewer 调写路由）
- **执行**: 查询审计日志
- **断言**: 两条事件均有记录，含主体标识、路由、结果、时间戳

### AC-14 回归（P0）

- **执行**: `pytest yuanzi-cli/tests mcp-yuanzi-bridge/tests atoms/tests`
- **断言**: 全量通过（当前基线 222 passed，新增鉴权测试只增不减）；既有 API 测试在有效 token 下全部适配通过

---

## 放行门禁

| 门禁 | 目标 |
|------|------|
| P0 检查点（AC-01/02/03/06/07/08/11/12/14） | 全部 Pass，**缺一不可** |
| P1 检查点（AC-04/05/09/10/13） | 允许 ≤ 1 项挂起，须在 BUG-025 行记录原因与跟进人 |
| 第三轮复检 | Audit 按本表逐项实证后，BUG-025 方可置 Closed |

> 本表已同步登记 `TEST-EXECUTION-TRACKING.csv`（TC-SEC-011 ~ TC-SEC-024，Status=Pending；TC-SEC-001~010 为首轮 OWASP 用例，已 Completed），执行时每完成一条即时回填，禁止批量补录。
