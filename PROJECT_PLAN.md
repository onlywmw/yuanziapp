:construction: **项目动态计划表** | 最后更新：2026-07-18

# Yuanzi 原子生态项目计划

> 把 MCP 服务器、工具、模块拆成独立"原子"，通过注册中心管理，在 Android 平板以知识图谱形式呈现。

---

## 项目总览

| 项目 | 内容 |
|------|------|
| 项目名称 | Yuanzi 原子生态 / 原子 App（Yuanzi App） |
| 当前阶段 | **第一阶段：开发体验基础设施** |
| 核心仓库 | `yuanzi-atom-templates`、`yuanzi-atoms`、`mcp-yuanzi-bridge`、`widgetmcp_src` |

---

## 里程碑路线图

| 里程碑 | 目标 | 预计完成 | 状态 |
|--------|------|----------|------|
| M1 | 原子开发基础设施就绪 | 2026-07-25 | :heavy_check_mark: 已完成 |
| M2 | 部署与配置管理就绪 | 2026-08-01 | :heavy_check_mark: 已完成 |
| M3 | 测试与质量门禁就绪 | 2026-08-08 | :heavy_check_mark: 已完成 |
| M4 | 注册中心服务化 | 2026-08-22 | :heavy_check_mark: 已完成 |
| M5 | 能力搜索与匹配 | 2026-09-05 | :white_circle: 未开始 |
| M6 | 安全与多租户 | 2026-09-19 | :white_circle: 未开始 |
| M7 | 原子市场与工作流 | 2026-10-10 | :white_circle: 未开始 |

---

## 第一阶段：开发体验基础设施

| 序号 | 任务 | 优先级 | 预计工期 | 状态 | 依赖 | 交付物 |
|------|------|--------|----------|------|------|--------|
| 1.1 | 定义 `meta.yaml` 规范 | P0 | 0.5 天 | :heavy_check_mark: 已完成 | 无 | 规范文档 |
| 1.2 | 创建标准化原子模板 | P0 | 1 天 | :heavy_check_mark: 已完成 | 1.1 | `yuanzi-atom-templates/` |
| 1.3 | 制作示例原子 `com.example.sum` | P0 | 0.5 天 | :heavy_check_mark: 已完成 | 1.2 | 可运行示例 |
| 1.4 | 示例原子在平板验证 | P0 | 0.5 天 | :heavy_check_mark: 已完成 | 1.3 | 测试报告 |
| 1.5 | 实现 `yuanzi-cli init` | P0 | 2 天 | :heavy_check_mark: 已完成 | 1.2 | CLI 命令 |
| 1.6 | 实现 `yuanzi-cli validate` | P0 | 1.5 天 | :heavy_check_mark: 已完成 | 1.5 | CLI 命令 |
| 1.7 | 实现 `yuanzi-cli test` | P0 | 1.5 天 | :heavy_check_mark: 已完成 | 1.5 | CLI 命令 |
| 1.8 | 实现 `yuanzi-cli build` | P1 | 1 天 | :white_circle: 未开始 | 1.7 | CLI 命令 |
| 1.9 | 实现 `yuanzi-cli publish --dry-run` | P1 | 1 天 | :white_circle: 未开始 | 1.8 | CLI 命令 |

### 甘特图

```
任务          | W1 (7.14-7.20) | W2 (7.21-7.27) |
--------------|----------------|----------------|
1.1 meta.yaml | ████           |                |
1.2 模板      | ██████         |                |
1.3 示例原子  | ████           |                |
1.4 平板验证  | ████           |                |
1.5-1.7 CLI   |                | ████████████   |
1.8-1.9 进阶  |                | ██████         |
```

---

## 第二阶段：部署与运维基础设施

| 序号 | 任务 | 优先级 | 预计工期 | 状态 | 依赖 | 交付物 |
|------|------|--------|----------|------|------|--------|
| 2.1 | 设计 `yuanzi-config.yaml` | P0 | 1 天 | :heavy_check_mark: 已完成 | 无 | 配置文件规范 |
| 2.2 | 实现 adb 一键同步脚本 | P0 | 1 天 | :heavy_check_mark: 已完成 | 2.1 | `scripts/sync-to-device.sh` |
| 2.3 | 配置 Syncthing 同步方案 | P1 | 1 天 | :white_circle: 未开始 | 2.1 | 同步配置文档 |
| 2.4 | 环境变量与密钥管理 | P0 | 1 天 | :white_circle: 未开始 | 2.1 | 密钥管理方案 |
| 2.5 | Termux 服务守护 | P1 | 2 天 | :white_circle: 未开始 | 2.2 | 守护脚本 |
| 2.6 | DB 自动备份 | P2 | 1 天 | :white_circle: 未开始 | 2.5 | 备份脚本 |

---

## 第三阶段：测试与质量门禁

| 序号 | 任务 | 优先级 | 预计工期 | 状态 | 依赖 | 交付物 |
|------|------|--------|----------|------|------|--------|
| 3.1 | 配置 black / ruff / mypy | P0 | 1 天 | :heavy_check_mark: 已完成 | 无 | 配置文件 |
| 3.2 | 配置 pytest 测试框架 | P0 | 1 天 | :heavy_check_mark: 已完成 | 无 | `tests/` 结构 |
| 3.3 | 配置 pre-commit 钩子 | P0 | 1 天 | :heavy_check_mark: 已完成 | 3.1, 3.2 | `.pre-commit-config.yaml` |
| 3.4 | 实现 `yuanzi install-hooks` | P1 | 0.5 天 | :heavy_check_mark: 已完成 | 3.3 | CLI 命令 |
| 3.5 | 原子 smoke test 规范 | P1 | 1 天 | :heavy_check_mark: 已完成 | 3.2 | `docs/atom-smoke-test-spec.md` |
| 3.6 | GitHub Actions CI 初版 | P2 | 2 天 | :heavy_check_mark: 已完成 | 3.3 | `.github/workflows/ci.yml` |

---

## 第四阶段：注册中心服务化

| 序号 | 任务 | 优先级 | 预计工期 | 状态 | 依赖 | 交付物 |
|------|------|--------|----------|------|------|--------|
| 4.1 | Schema 迁移系统 | P0 | 2 天 | :heavy_check_mark: 已完成 | 无 | `migrations/` |
| 4.2 | 原子版本化表 | P0 | 2 天 | :heavy_check_mark: 已完成 | 4.1 | `atom_versions` |
| 4.3 | REST API（FastAPI） | P0 | 3 天 | :heavy_check_mark: 已完成 | 4.2 | `api.py` |
| 4.4 | 健康探针系统 | P1 | 2 天 | :heavy_check_mark: 已完成 | 4.3 | probe 服务 |
| 4.5 | 依赖图解析 | P1 | 2 天 | :heavy_check_mark: 已完成 | 4.2 | `resolve_dependencies()` |
| 4.6 | 修复分类误判 | P1 | 1 天 | :heavy_check_mark: 已完成 | 无 | 更新后的分类 |

---

## 第五阶段：能力搜索与匹配

| 序号 | 任务 | 优先级 | 预计工期 | 状态 | 依赖 | 交付物 |
|------|------|--------|----------|------|------|--------|
| 5.1 | function embedding 生成 | P0 | 3 天 | :white_circle: 未开始 | 4.3 | embedding 表 |
| 5.2 | 语义搜索 API | P0 | 2 天 | :white_circle: 未开始 | 5.1 | `/search` 端点 |
| 5.3 | 原子组合推荐 | P1 | 3 天 | :white_circle: 未开始 | 5.2 | 组合算法 |
| 5.4 | Widget MCP 集成搜索 | P1 | 2 天 | :white_circle: 未开始 | 5.2 | UI 搜索入口 |

---

## 第六阶段：安全与多租户

| 序号 | 任务 | 优先级 | 预计工期 | 状态 | 依赖 | 交付物 |
|------|------|--------|----------|------|------|--------|
| 6.1 | API Key 认证 | P0 | 2 天 | :white_circle: 未开始 | 4.3 | 认证中间件 |
| 6.2 | RBAC 权限模型 | P1 | 3 天 | :white_circle: 未开始 | 6.1 | 权限系统 |
| 6.3 | 原子签名验证 | P1 | 3 天 | :white_circle: 未开始 | 4.2 | 签名模块 |
| 6.4 | 审计日志哈希链 | P2 | 2 天 | :white_circle: 未开始 | 现有审计表 | 防篡改审计 |

---

## 第七阶段：原子市场与工作流

| 序号 | 任务 | 优先级 | 预计工期 | 状态 | 依赖 | 交付物 |
|------|------|--------|----------|------|------|--------|
| 7.1 | 原子评分与评论 | P2 | 2 天 | :white_circle: 未开始 | 4.3 | 评分系统 |
| 7.2 | 工作流 DAG 定义 | P1 | 3 天 | :white_circle: 未开始 | 4.5 | 工作流 schema |
| 7.3 | 工作流执行引擎 | P1 | 4 天 | :white_circle: 未开始 | 7.2 | 执行器 |
| 7.4 | 联邦注册中心 | P2 | 5 天 | :white_circle: 未开始 | 6.3 | 联邦协议 |

---

## 当前重点关注（接下来 2 周）

| 任务 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| `yuanzi-cli init/validate/test` | P0 | :heavy_check_mark: 已完成 | 第一阶段核心，直接决定造原子体验 |
| pre-commit + 代码格式化 | P0 | :heavy_check_mark: 已完成 | 代码质量门禁 |
| `yuanzi install-hooks` CLI 命令 | P1 | :heavy_check_mark: 已完成 | 把钩子安装收进 yuanzi-cli |
| GitHub Actions CI 初版 | P2 | :heavy_check_mark: 已完成 | 提交时自动跑检查 |
| pre-commit + 代码格式化 | P0 | :white_circle: 未开始 | 代码质量门禁 |
| 修复原子分类误判 | P1 | :heavy_check_mark: 已完成 | 提升图谱分组准确性 |

---

## 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Termux 环境重置 | 高 | 用脚本化部署 + 定期 DB 备份 |
| 平板端口冲突 | 中 | 原子端口支持环境变量覆盖 |
| 分类算法持续误判 | 中 | 引入 LLM 分类 + 人工复核队列 |
| CLI 设计过度工程 | 中 | 坚持 MVP，先支持 5 个核心命令 |
