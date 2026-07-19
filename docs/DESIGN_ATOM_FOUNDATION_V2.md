# 原子基座夯实 v2

> **定位**: 原子体系 7 项硬规范 + 专家评审补充
> **来源**: DESIGN_ATOM_FOUNDATION.md + 两轮专家反馈
> **版本**: v2.1 (打磨版)

---

## 1. 生命周期

### 灰度发布

```
`draft` → `review` → `registered` → `canary` → `running`

`canary` 状态:
  · 只接收 10% 流量
  · 探针 + 用户反馈确认稳定
  · 3 天后自动 → `running`

退出灰度:
  · 稳定 → `running` (全量)
  · 异常 → 自动 rollback 到上一版本

`rollback` 时自动记录:
  · 回滚原因 (触发指标: 错误率/延迟/P99)
  · 影响版本 (从哪个版本回滚)
  · 时间戳

回滚记录供后续分析——哪些原子经常回滚、什么原因。
```

### 健康度评分

```
不再只看 `probe_ok` 或 `probe_fail` 的二元判断。

健康指标实时采集，按固定周期（每日）计算评分:

  健康度 = 成功率(40%) + 响应延迟(30%) + 故障次数(20%) + 依赖健康(10%)

  分数范围    状态              动作
  ───────────────────────────────────────
  ≥ 90 分     `running`         正常
  70-89 分    `running` + ⚠️    建议关注
  50-69 分    `degraded`        降级, 建议修复
  < 50 分     `offline`         自动

采集是持续的, 评分是按日的。不丢失精度, 也不过度消耗。
```

---

## 2. I/O Schema

### 流式与大文件

```
类型名称统一小写:

  `json`      结构化小数据 (默认)
  `stream`    视频流、大批量数据 (不进内存)
  `file_ref`  对象存储 URL, 指向 S3 或本地路径

系统处理:
  · `stream` 类型不参与内存加载 (避免 OOM)
  · `file_ref` 指向临时存储 (工作流结束后自动清理)
  · 连线时 `stream` 只能连 `stream`, 类型不匹配 → 红线提示
```

### 性能基准

```json
{
  "performance": {
    "avg_latency_ms": 120,
    "p99_latency_ms": 500,
    "max_qps": 50,
    "memory_mb": 64,
    "streaming_supported": false
  }
}
```

```
测量条件 (统一口径):
  · 单次执行 (非并发)
  · 默认硬件 (标准 Android 设备)
  · 非首次 (预热后)

为什么需要:
  工作流编排者设置 `timeout` 时:
    知道 avg=120ms → `timeout` 设 2s 合理
    知道 max_qps=50 → 并发不超过 50
  调度器自动优化:
    高 QPS 原子 → 并行执行
    高延迟原子 → 放到工作流开头先跑
```

---

## 3. 分类扩展字段

原子 `classification` 下新增可选字段, 用于描述原子的使用场景和风格,
帮助搜索、推荐和展示。

| 字段 | 类型 | 说明 |
|------|------|------|
| style | string[] | 风格标签, 最多 3 个。可选值: 极简/可靠/专业/优雅/强大/轻量/创意/温馨/硬核/极客/玩趣/实验 |
| audience | string[] | 目标受众, 最多 3 个。可选值: 后端开发/前端开发/数据工程/设计师/作家/学生/所有人/极客/运维/研究员/创作者 |
| mood | string | 使用基调, 单选。可选值: 专注/平静/精力充沛/轻松愉快/严肃认真/受启发 |
| quality | string | 品质等级, 单选。默认 functional。可选值: experimental/functional/polished/battle-tested/handcrafted |
| use_case | string[] | 使用场景, 最多 3 个。可选值: 日常工作/生产环境/学习/原型开发/创意项目/紧急救火 |
| narrative | string | 作者手写叙事, 10-200 字 |

```
校验规则:
  - style/audience/use_case 超过上限 → 拒绝注册
  - narrative 和 description 完全一致 → 警告
  - narrative 含明显占位词 (test/测试/123/todo) → 警告
  - quality=handcrafted → Audit 审核
  - quality=experimental 且 use_case=production → 冲突警告
```

所有字段可选, 不填不影响注册。

---

## 4. 版本语义

### 自动废弃通知

```
原子 `deprecated` 时, 系统自动:

  1. 解析依赖图谱 → 找到所有引用此原子的工作流和原子
  2. 通过站内信通知每个下游作者:
     "你依赖的 mcp.postgres@1.2.0 已废弃,
      推荐升级到 mcp.postgres@2.0.0"
  3. 如果作者提供了 `replaced_by` 字段 → 自动推荐替代原子
  4. 通知频率: 废弃时 ×1, 1 个月后 ×1, 退役前 1 周 ×1
```

### 冻结期

```
`deprecated` → `retired` 不是硬编码 3 个月自动退役。

  第 1 月: 标记 `deprecated`, 通知所有下游
  第 2 月:
    · 调用量超过系统阈值 → 延长窗口
    · 系统强制要求作者提供升级指南
  第 3 月:
    · 调用量低于退役阈值 → 允许退役
    · 仍高于阈值 → 标记为 `frozen` (只读, 不退役)

阈值可配置, 不写死在文档中。
```

---

## 5. 安全分级

```
L0 纯计算    无敏感操作, 结果可公开         math-calc, string-split, date-time
L1 只读      可读取本地数据                 file-read, location, weather
L2 读写/网络  可写入/可联网/可感知外设       file-write, http-get, camera, device
L3 特权      可加密/解密/访问密钥           encrypt-aes, decrypt-aes, hash-digest
L4 系统级    可执行系统操作                 rule-engine, notification

原子类型 → 最低安全级别:
  tool:      按具体功能 (file-read=L1, math-calc=L0)
  sensor:    ≥L1 (采集数据)
  fusion:    ≥L1
  rule:      ≥L2 (做出决策)
  actuator:  ≥L2 (改变状态)
  connector: ≥L1 (借用平台能力)

交叉检查:
  · L4 依赖的原子必须 ≥ L3
  · L3 依赖的原子必须 ≥ L2
  · 不允许 L4 依赖 L0 (安全降级)
```

## 6. 安全加固

### 一键修复

```
检测到安全降级 (L4 依赖 L2):

  不只是警告 — 系统主动建议:

  ┌──────────────────────────────────────────┐
  │  ⚠️ 安全降级检测                          │
  │                                          │
  │  encrypt-aes (L3) 的输入来自              │
  │  http-get (L2)                           │
  │                                          │
  │  建议在中间插入校验原子:                   │
  │  [system.string-match] (L1) ✓            │
  │  [system.json-parse]   (L1) ✓            │
  │                                          │
  │  [预览变更]  [忽略]                      │
  └──────────────────────────────────────────┘

  点击 [预览变更] → 展示插入后的工作流拓扑
  确认 → 自动插入校验原子 + 连线重组
  取消 → 保持原状

自动改工作流是大的动作, 必须预览后确认。
一键修复仅适用于 `pure` 原子之间的链路。涉及 `impure` 原子（有副作用）的链路, 不自动插入校验原子, 改为提示作者手动修复。
```

### 依赖风险

```
注册或使用原子 A 时, 系统分析其依赖的健康状况:

  综合风险 = Σ(依赖权重 × 健康评分)

  综合风险 = Σ(依赖权重 × 健康评分)

  A 依赖:
    B (running, 健康度 95)  ✅  权重 1, 贡献 95
    C (degraded, 健康度 60) ⚠️  权重 1, 贡献 60
    D (deprecated)          ❌  权重 2, 贡献 0

  综合风险: 高 (2/3 依赖有问题)
  建议: 替换 D, 关注 C
```

---

## 6. 测试

### 沙箱执行

```
L2 (敏感) 及以上原子在测试时:

  Unit Test:
    file-read  → 虚拟文件系统, 不触碰真实文件
    http-get   → HTTP Mock Server, 不发起真实网络请求
    encrypt    → 隔离的密钥存储, 不触碰系统密钥

  Integration Test:
    全链路在沙箱中运行
    外部依赖用 Mock (数据库、API、文件系统)

  E2E Test:
    在隔离的 Android 模拟器中运行
    不污染生产数据
```

### 覆盖率

```
★★★☆☆ `functional`:
  + smoke 测试通过 (已有)
  + contract 测试通过 (已有)
  + I/O 输入组合覆盖率 ≥ 80%
    (80% 的输入字段组合被测试覆盖)

★★★★☆ `complete`:
  + Unit 测试行覆盖率 ≥ 70%
  + 所有 public 函数至少一个测试用例

★★★★★ `exceptional`:
  + 行覆盖率 ≥ 90%
  + 错误路径也全部覆盖

注: "I/O 输入组合覆盖率" 不是代码路径覆盖率。
指 "这个原子有 10 种可能的输入组合, 测试覆盖了其中 8 种 = 80%"。
```

---

## 7. 星级

### SLA 指标

```
★★★★★ `exceptional` 的新门槛:

  不只是文档好、评分高, 还要真实运行过:

  过去 30 天内:
    · 可用性 ≥ 99.9% (probe 成功率)
    · P99 延迟 ≤ 声明的 p99_latency_ms
    · 故障恢复时间 ≤ 5 分钟

  数据来源: 探针系统每日记录的 runtime_json
  不是作者自己填 — 系统实测。
```

### 副作用标签

```
  `pure`    无副作用, 无状态       math-calc, string-split, json-parse
            → 可安全并行, 可重试, 可缓存结果
            → 星级 +0.5 权重

  `impure`  有副作用或依赖外部     http-get, file-write, location
            (默认值, 未声明时自动归入)
            → 不可缓存, 重试需谨慎
```

---

## 8. CLI 脚手架

```
yuanzi atom init weather-sensor

  生成 (统一排序):
    weather-sensor/
    ├── core.py              ← handler(data) 模板
    ├── meta.json            ← I/O schema 空白模板
    ├── server.py            ← /health /meta /run 标准端点
    ├── Dockerfile
    ├── requirements.txt
    └── tests/
        ├── test_smoke.py    ← 自动生成的 smoke 测试
        └── test_contract.py ← 自动生成的 contract 测试

一条命令, 7 个文件。排序固定, 所有原子一致。
```

---

## 实施优先级

```
P0 (立即):
  基础能力:
    I/O Schema 标准化 + 注册验证
    脚手架 CLI (atom init)
    副作用标签 (`pure` / `impure`, 默认 `impure`)

P1 (1-2 周):
  平台能力:
    健康度评分 (实时采集 + 按日计算)
    废弃通知系统
    安全降级一键修复 (预览 → 确认)
    沙箱测试环境

P2 (后续):
  自动化能力:
    灰度发布 (`canary`)
    流式 I/O 支持
    性能基准声明
    SLA 入星级
```

---

> **v2.1 — 打磨版。不新增内容, 只让已有的更准确、更统一、更可执行。**
