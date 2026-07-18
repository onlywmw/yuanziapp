"""Yuanzi AI Agent Team Configuration — Python edition.

No YAML parsing needed.  Directly importable by scheduler.py.
"""

from __future__ import annotations

from typing import Any, Dict, List

# ---- 角色定义 ----
ROLES: Dict[str, Dict[str, str]] = {
    "hub": {
        "name": "Hub",
        "role_file": "agent_hub_role.md",
        "description": "管家/调度器，管理任务分发和进度追踪",
    },
    "arch": {
        "name": "Arch",
        "role_file": "agent_architect_role.md",
        "description": "架构师/设计师，技术方案设计",
    },
    "eng": {
        "name": "Eng",
        "role_file": "agent_engineer_role.md",
        "description": "工程师/开发者，代码实现",
    },
    "audit": {
        "name": "Audit",
        "role_file": "agent_audit_role.md",
        "description": "审查员/QA，代码审查",
    },
    "fixer": {
        "name": "Fixer",
        "role_file": "agent_fixer_role.md",
        "description": "修复者/应急响应，CI 故障和紧急 Bug",
    },
}

# ---- 信号路由表 ----
# Issue 标题/正文中检测到信号 → 触发对应动作
SIGNALS: List[Dict[str, Any]] = [
    {
        "pattern": "📐 design-ready",
        "description": "Arch 设计完成",
        "triggered_by": "arch",
        "route_to": "eng",
        "add_label": "ready-for-dev",
        "comment": """## 🔧 任务就绪 — 待 Eng 领取

**信号**: 📐 design-ready — Arch 设计已完成

**Eng 行动清单**:
1. 阅读设计文档（如 Issue 中链接的 `docs/DESIGN_*.md`）
2. 阅读角色规范 `.ai-agents/agent_engineer_role.md`
3. 在此 Issue 下评论 `🔧 in-progress` 认领任务
4. 按照设计文档的子任务顺序实施
5. 完成后提交 PR，添加 `👀 review-requested` 信号

@{sender} @Hub 已分发至 Eng""",
    },
    {
        "pattern": "🔧 in-progress",
        "description": "Eng 开始编码",
        "triggered_by": "eng",
        "route_to": "hub",
        "add_label": "in-progress",
        "remove_label": "ready-for-dev",
        "comment": """## 🔧 开发进行中 — {sender} 已认领

任务进入开发阶段。请 Eng 评估预计完成时间并回复。

开发完成后提交 PR 并发出 `👀 review-requested` 信号。

@Hub 已记录，将定期检查进度。""",
    },
    {
        "pattern": "👀 review-requested",
        "description": "Eng 请求审查",
        "triggered_by": "eng",
        "route_to": "audit",
        "add_label": "under-review",
        "remove_label": "in-progress",
        "comment": """## 👀 代码审查请求

**Audit 审查清单** (详见 `.ai-agents/agent_audit_role.md`):
1. **正确性**: 代码是否正确实现了 Arch 的设计意图？
2. **安全性**: 有无 SQL 注入、明文密钥、权限绕过？
3. **性能**: 有无 N+1 查询、内存泄漏？
4. **兼容性**: 是否破坏了现有 API/Schema/数据结构？

审查完成后请添加 `✅ approved` 或 `❌ rejected` 信号。

@{sender} @Hub 已通知 Audit""",
    },
    {
        "pattern": "✅ approved",
        "description": "审查通过",
        "triggered_by": "audit",
        "route_to": "hub",
        "add_label": "ready-to-merge",
        "remove_label": "under-review",
        "comment": """## ✅ 审查通过

PR 已通过审查，可合并至 main。

@{sender} @Hub Issue 待关闭，任务完成。""",
    },
    {
        "pattern": "❌ rejected",
        "description": "审查驳回",
        "triggered_by": "audit",
        "route_to": "eng",
        "add_label": "needs-fix",
        "remove_label": "under-review",
        "comment": """## ❌ 审查驳回 — 需修复

请 Eng 根据 Audit 的具体反馈修改代码。修复完成后重新发出 `👀 review-requested` 信号。

@{sender} @Hub 已通知 Eng""",
    },
    {
        "pattern": "🚨 ci-failed",
        "description": "CI 失败",
        "triggered_by": "ci",
        "route_to": "fixer",
        "add_label": "ci-failed",
        "comment": """## 🚨 CI 故障 — Fixer 应急响应

请 Fixer 按照 `.ai-agents/agent_fixer_role.md` 的故障分类流程处理:
1. 分析 CI 日志
2. 定位根因
3. 实施最小化修复
4. 评论 `✅ resolved` 表示修复完成

处理期间相关 PR 合并暂停。

@{sender} @Hub 已通知 Fixer""",
    },
    {
        "pattern": "🚨 investigating",
        "description": "Fixer 开始排查",
        "triggered_by": "fixer",
        "route_to": "hub",
        "add_label": "investigating",
        "comment": """## 🚨 故障排查中 — {sender} 正在定位根因

排查期间相关 PR 合并暂停。修复完成后请发出 `✅ resolved` 信号。

@Hub 已记录""",
    },
    {
        "pattern": "✅ resolved",
        "description": "故障修复完成",
        "triggered_by": "fixer",
        "route_to": "hub",
        "add_label": "resolved",
        "remove_label": "investigating",
        "remove_label": "ci-failed",
        "remove_label": "needs-fix",
        "comment": """## ✅ 故障已修复

工作流恢复正常。相关阻塞已解除。

@{sender} @Hub 恢复正常流程""",
    },
]
