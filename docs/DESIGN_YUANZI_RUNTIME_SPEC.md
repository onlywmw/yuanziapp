# Yuanzi Runtime Specification (YRS)

> **定位**: 从原子规范升级为运行时平台标准 —— 调度、治理、运维、商业化统一基础
> **来源**: DESIGN_ATOM_FOUNDATION.md → v2 专家评审 → YRS v1
> **原则**: 每一个规范都有调度器能自动执行的检查代码

---

# 第一部分: 原子声明 (P0)

## 1. 能力声明

调度器最需要知道——能不能重试、能不能并发、能不能缓存。

```json
{
  "capability": {
    "parallel": true,
    "reentrant": true,
    "idempotent": false,
    "retryable": true,
    "cacheable": false
  }
}
```

| 字段 | 含义 | 影响 |
|------|------|------|
| parallel | 能不能并发执行多个实例 | false → 工作流中此原子只能串行 |
| reentrant | 正在跑的时候能不能再来一个 | false → 调度器排队 |
| idempotent | 跑两次结果一样 | true → 容错 retry 是安全的 |
| retryable | 失败后能不能重试 | false → 不容错, 失败直接 abort |
| cacheable | 相同输入能不能缓存结果 | true → 调度器自动缓存, 省调用 |

```
示例:
  math-calc:      parallel=true,  idempotent=true,  cacheable=true
  http-get:       parallel=true,  retryable=true,   cacheable=true
  支付原子:        parallel=false, retryable=false,   cacheable=false
  file-write:     parallel=false, reentrant=false
```

## 2. 资源锁

有些资源不能同时被两个工作流使用。

```json
{
  "resource": {
    "exclusive": ["filesystem", "camera", "bluetooth", "database:mysql"]
  }
}
```

```
调度器行为:
  工作流 A 用了 file-write (exclusive=filesystem)
  工作流 B 也要用 file-write
  → 调度器自动排队 B, 等 A 完成再执行

资源命名:
  filesystem       文件系统
  camera           摄像头
  bluetooth        蓝牙
  gps              GPS
  database:mysql   指定数据库实例
  database:postgres
```

## 3. 超时策略

不只声明 latency——声明超时时怎么办。

```json
{
  "timeout": {
    "default_seconds": 30,
    "max_seconds": 300,
    "cancelable": true,
    "graceful_shutdown": true,
    "cleanup": true
  }
}
```

| 字段 | 含义 |
|------|------|
| default_seconds | 默认超时, 工作流作者可覆盖 |
| max_seconds | 硬上限, 不可超越 |
| cancelable | 超时后能不能取消 |
| graceful_shutdown | 取消时能不能优雅关闭 (等正在做的完成) |
| cleanup | 取消后要不要清理临时文件/连接 |

## 4. 错误体系

统一的错误码, AI 才能自动修复。

```
错误码规则: CATEGORY_NNN

CATEGORY:
  USER      用户输入错误 (修输入即可)
  SCHEMA    I/O schema 不匹配
  NETWORK   网络/外部 API 错误 (可重试)
  DEP       依赖原子错误
  PERM      权限不足
  INTERNAL  原子内部错误 (需要作者修)

示例:
  USER_001   缺少必填字段
  USER_002   字段类型错误
  NETWORK_101  连接超时
  NETWORK_102  DNS 解析失败
  PERM_501   无权访问文件
  INTERNAL_901  未知内部错误
```

### 为什么需要

```
现在: probe_atom → "failed" → 不知道什么原因

有错误码后:
  NETWORK_101 → 调度器知道: "连接超时, 可以用 retry"
  PERM_501 → 调度器知道: "权限不够, 不能重试, 通知作者"
  USER_001 → 调度器知道: "输入有问题, 通知用户修正"
```

---

# 第二部分: 运行时治理 (P1)

## 5. 事件生命周期

每个原子在工作流中运行时, 发出标准事件。

```
before_run  → running → progress → completed
                           │
                           ├→ failed
                           ├→ cancelled
                           └→ rollback

事件格式:
  {
    "event": "progress",
    "atom_id": "system.http-get",
    "run_id": "run_abc123",
    "progress_pct": 34,
    "message": "Downloading... 34MB/100MB",
    "timestamp": "..."
  }
```

UI 可以实时显示进度条, 而不是只看到"运行中"。

## 6. 运行时指标

健康度评分的数据来源。

```json
{
  "metrics": {
    "cpu_percent": 23,
    "memory_mb": 80,
    "fd_count": 12,
    "network_bytes_in": 1024000,
    "cache_hit_rate": 0.85,
    "queue_depth": 3
  }
}
```

```
每次执行后更新 runtime_json.metrics。
长期积累 → 自动扩容建议。
```

## 7. 配额

```json
{
  "quota": {
    "daily_calls": 1000,
    "qps": 10,
    "tokens_per_call": 100,
    "bandwidth_mb_per_day": 500
  }
}
```

```
调度器:
  到达配额 → 排队或拒绝, 不崩溃
  GPT 原子每天 1000 次 → 达到 → 返回 "QUOTA_EXCEEDED"
```

## 8. 成本

```json
{
  "cost": {
    "per_call_usd": 0.001,
    "per_token_usd": 0.00001,
    "gpu_seconds": 2
  }
}
```

```
工作流编辑器:
  拖入原子 → 实时显示预估成本
  整个工作流 → 总预估: $0.53

商业化:
  作者为自己的原子定价
  平台抽成
```

---

# 第三部分: 可靠性与兼容性 (P2)

## 9. 原子事务

```json
{
  "transaction": {
    "supports_rollback": true,
    "rollback_handler": "rollback"
  }
}
```

```
工作流: A → B → C
  B 失败, 且 A.supports_rollback=true
  → 调度器调用 A.rollback()
  → A 撤销自己的副作用

只有声明了 rollback 的原子才能组成事务工作流。
```

## 10. 兼容性矩阵

```json
{
  "compatibility": {
    "runtime": ">=2.0",
    "python": ">=3.12",
    "android": ">=11",
    "ios": ">=16"
  }
}
```

```
安装原子前 → 检查设备是否满足兼容性
不满足 → 提示 "需要 Android 11+"
```

## 11. 依赖锁定

```
不只是 @^1.0——要锁定精确版本, 且记录校验和。

注册时:
  dependencies: ["system.http-get@2.1.3"]

同时记录:
  dependency_lock: {
    "system.http-get@2.1.3": {
      "signature_hash": "abc123...",
      "resolved_at": "2026-07-19"
    }
  }

升级时:
  yuanzi update --dry-run → 列出所有依赖变化
  yuanzi update → 更新 lock 文件
```

## 12. 许可证

```json
{
  "ownership": {
    "license": "MIT",
    "license_url": "https://opensource.org/licenses/MIT"
  }
}
```

```
license 枚举:
  MIT, Apache-2.0, GPL-3.0, BSD-3-Clause, Commercial

Commercial → 需要付费才能使用
企业用原子前 → 检查 license → GPL 可能不合规
```

---

# 第四部分: 平台演进 (P3)

## 13. 策略引擎

不是把权限写死在原子里——是动态策略。

```
策略: "L3 及以上原子, 在非工作时间 (22:00-06:00) 不允许执行"
策略: "写文件原子, 必须由人工确认后才能运行"
策略: "外部 API 原子, 每天限 1000 次, 超过需审批"

策略引擎在工作流执行前检查所有策略。
不通过 → 拒绝执行 + 通知原因。
```

## 14. 功能开关

```
原子可以灰度开启:

  canary:
    用户 A, B: 使用 v2 (新版本)
    其他用户: 使用 v1 (稳定版本)

开关可按: 用户/租户/版本/地区
有异常 → 一键关闭 v2 → 全部回退 v1
```

## 15. 运行快照

```
工作流异常时的自动现场保存:

  snapshot:
    inputs: {...}        ← 输入参数
    outputs: {...}       ← 到目前为止的输出
    context: {...}       ← 上下文
    dependency_versions: {...}  ← 每个依赖的精确版本

一键复现:
  yuanzi workflow replay --snapshot snap_abc123
  → 在隔离环境中重放 → 看哪里出了问题
```

## 16. 链路追踪

```
每次原子调用 → 生成 trace_id → 全链路追踪:

  workflow_id: wf_001
    ├── trace: location → 120ms ✅
    ├── trace: weather → 230ms ✅
    ├── trace: camera → TIMEOUT ⚠️
    ├── trace: fusion → 45ms ✅
    └── trace: music → 80ms ✅

标准: OpenTelemetry / W3C Trace Context
用途: 性能分析 + 故障定位
```

## 17. 审计日志

```
敏感操作记完整审计:

  {
    "trace_id": "abc123",
    "atom_id": "system.file-write",
    "caller": "workflow:coffee_shop_music",
    "params_summary": "path=/music/playlist.json, size=2KB",
    "result": "success",
    "timestamp": "...",
    "user": "张三"
  }

满足:
  · 企业合规审计
  · 故障回溯
  · 安全事件调查
```

---

# 实施优先级总结

```
P0 (立即):
  能力声明 (Capability)        → 调度器智能化
  资源锁 (Resource Lock)       → 防并发冲突
  超时策略 (Timeout Policy)    → 工作流不被卡死
  错误体系 (Error Taxonomy)    → AI 可自动修复

P1 (1-2 周):
  事件生命周期                  → UI 实时进度
  运行时指标                    → 健康度评分数据源
  配额 + 成本                   → 商业化基础

P2 (后续):
  原子事务 (Rollback)           → 可靠工作流
  兼容性矩阵 + 依赖锁定          → 不炸库
  许可证                        → 企业合规

P3 (平台):
  策略引擎 + 功能开关 + 快照 + Trace + 审计
  → 企业级平台能力
```

---

> **YRS v1 — 从"原子怎么写"升级为"平台怎么跑"。**
> **每一个规范都有调度器能自动执行的检查代码。规范不是文档——是可验证的约束。**
