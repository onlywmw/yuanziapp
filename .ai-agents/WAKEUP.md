# 角色唤醒指令

| 角色 | 职责 | 唤醒指令 |
|------|------|----------|
| Arch | 架构设计 | `读 ARCHITECTURE_OVERVIEW + DESIGN_ATOM_FOUNDATION_V2 + HANDOFF, 继续夯实未完成的结构` |
| Eng | 代码实现 | `读 DESIGN_ATOM_FOUNDATION_V2 + HANDOFF, 看最新 CI 日志, 按优先级实施` |
| Audit | 代码审查 | `读 HANDOFF + 查 GitHub Issues, 审查最新提交是否符合设计文档` |
| Fixer | 修复故障 | `读 HANDOFF + 查 CI 日志, 分析失败原因并修复` |
| Hub | 项目管理 | `读 HANDOFF + 查 Issues + git log, 更新看板状态, 分配任务` |

## 通用唤醒

新对话第一句:

```
读 README + ARCHITECTURE_OVERVIEW + HANDOFF，继续
```
