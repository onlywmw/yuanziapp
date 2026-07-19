# 原子基座夯实 v2

> **定位**: 原子体系 7 项硬规范 + 专家评审补充
> **来源**: DESIGN_ATOM_FOUNDATION.md + 专家反馈 14 项优化
> **新增**: 灰度发布、健康评分、流式 I/O、性能基准、废弃通知、沙箱测试、SLA、脚手架

---

## 1. 生命周期 (增强)

### 新增: 灰度发布

```
draft → review → registered → canary → running
                                  │
                                  └─ 只接收 10% 流量
                                     探针 + 用户反馈确认稳定
                                     3 天后自动 → running

deprecated 推出新版时:
  v1 (deprecated) ──→ v2 (canary, 20% 流量)
  稳定 → v2 → running (100%)
  有问题 → v2 → rollback → v1 恢复 running
```

### 新增: 健康度评分

```
不再只看 "probe_ok" 或 "probe_fail" 的二元判断。

健康度 = 成功率(40%) + 响应延迟(30%) + 故障次数(20%) + 依赖健康(10%)

  ≥ 90 分: running (正常)
  70-89:   running + ⚠️ 预警 (建议关注)
  50-69:   degraded (降级, 建议修复)
  < 50:    offline (自动, 不需要等连续 3 次失败)

每天更新一次, 不依赖探针的单点检测。
```

---

## 2. I/O Schema (增强)

### 新增: 流式与大文件支持

```
当前 JSON Schema 适合结构化小数据。

新增 stream 类型:
  io.input.type = "stream"    → 视频流、大批量数据
  io.input.type = "file_ref"  → 对象存储 URL (S3/本地路径)
  io.output.type = "file_ref" → 处理后文件的 URL

系统处理:
  · stream 类型不参与内存加载 (避免 OOM)
  · file_ref 指向临时存储 (工作流结束后自动清理)
  · 连线时 stream 只能连 stream (不能把视频流传给 JSON 解析器)
```

### 新增: 性能基准声明

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
为什么需要:
  工作流编排者设置 timeout 时:
    知道 avg=120ms → timeout 设 2s 合理
    知道 max_qps=50 → 并发不要超过 50

  调度器自动优化:
    多个高 QPS 原子 → 并行执行
    单个高延迟原子 → 放到工作流开头, 先跑
```

---

## 3. 版本语义 (增强)

### 新增: 自动废弃通知

```
原子 deprecated 时, 系统自动:

  1. 解析依赖图谱 → 找到所有引用此原子的工作流和原子
  2. 通过站内信通知每个下游作者:
     "你依赖的 mcp.postgres@1.2.0 已废弃,
      推荐升级到 mcp.postgres@2.0.0"
  3. 如果作者提供了 replaced_by 字段 → 自动推荐替代原子
  4. 通知频率: 废弃时 ×1, 1 个月后 ×1, 退役前 1 周 ×1
```

### 新增: 强制冻结期

```
deprecated → retired 不是 3 个月自动退役。

  第 1 月: 标记 deprecated, 通知所有下游
  第 2 月: 
    · 如果仍有大量调用 (>100次/天) → 延长窗口
    · 系统强制要求作者提供升级指南
  第 3 月:
    · 调用量 <10次/天 → 允许退役
    · 仍有调用 → 标记为 frozen (只读, 不退役)
```

---

## 4. 依赖约束与安全 (增强)

### 新增: 安全降级一键修复

```
当检测到安全降级 (L4 依赖 L2):

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
  │  [一键插入]  [忽略]  [了解更多]           │
  └──────────────────────────────────────────┘

  点击 [一键插入] → 工作流画布自动插入校验原子 → 连线自动重组
```

### 新增: 依赖风险预估

```
注册或使用原子 A 时, 系统分析其依赖的健康状况:

  A 依赖:
    B (running, 健康度 95)  ✅
    C (offline, 最后探测 2h 前)  ⚠️
    D (deprecated, 推荐替换)     ❌

  综合风险: 高 (2/3 依赖有问题)
  建议: 替换 C 或等待恢复, 替换 D
```

---

## 5. 测试分层 (增强)

### 新增: 沙箱执行

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

沙箱 = Docker 容器 (本地) / Android Emulator (APK)
```

### 新增: 测试覆盖率入星级

```
★★★☆☆ functional:
  + smoke 测试通过 (已有)
  + contract 测试通过 (已有)
  + I/O schema 路径覆盖率 ≥ 80% (新增)
    意思是: 80% 的输入字段组合被测试覆盖

★★★★☆ complete:
  + Unit 测试行覆盖率 ≥ 70%
  + 所有 public 函数至少一个测试用例

★★★★★ exceptional:
  + 行覆盖率 ≥ 90%
  + 错误路径也全部覆盖
```

---

## 6. 完整度星级 (增强)

### 新增: SLA 指标

```
★★★★★ exceptional 的新门槛:

  不只是文档好、评分高, 还要真实运行过:

  过去 30 天内:
    · 可用性 ≥ 99.9% (probe 成功率)
    · P99 延迟 ≤ 声明的 p99_latency_ms
    · 故障恢复时间 ≤ 5 分钟

  数据来源: 探针系统每日记录的 runtime_json
  不是作者自己填的 — 是系统实测的
```

### 新增: 副作用标签

```
每个原子标记:

  pure    无副作用, 无状态       math-calc, string-split, json-parse
          → 可安全并行, 可重试, 可缓存结果
          → 星级 +0.5 权重

  impure  有副作用或依赖外部     http-get, file-write, location
          → 不可缓存, 重试需谨慎
          → 无额外权重
```

---

## 7. 实施工具 (新增)

### 脚手架 CLI

```
yuanzi atom init weather-sensor

  生成:
    weather-sensor/
    ├── core.py              ← handler(data) 模板
    ├── server.py            ← /health /meta /run 标准端点
    ├── meta.json            ← I/O schema 空白模板
    ├── tests/
    │   ├── test_smoke.py    ← 自动生成的 smoke 测试
    │   └── test_contract.py ← 自动生成的 contract 测试
    ├── Dockerfile
    └── requirements.txt

  一条命令, 5 个文件, 规范落地。
```

### 可视化依赖与安全图谱

```
不是文本, 是图。

  编排工作流时, 画布右侧有安全视图:

    ┌──────────────────────────────────────┐
    │  工作流: 咖啡厅音乐                   │
    │                                      │
    │  http-get (L2) ──→ encrypt (L3)      │
    │       │                              │
    │       ├──→ json-parse (L1)           │
    │       │                              │
    │       └──→ file-write (L2)           │
    │                                      │
    │  ⚠️ 1 处安全降级 (L2→L3)              │
    │  依赖健康: 3/3 ✅                     │
    │  版本冲突: 无                         │
    └──────────────────────────────────────┘

  颜色编码:
    绿色连线 = 安全级别合规
    黄色连线 = 安全降级, 已警告
    红色连线 = 循环依赖 / 缺失依赖
```

---

## 实施优先级

```
P0 (立即):
  I/O Schema 标准化 + 注册验证
  脚手架 CLI (atom init)
  副作用标签 (pure/impure)

P1 (1-2 周):
  健康度评分 (替代二元探针)
  废弃通知系统
  安全降级一键修复
  沙箱测试环境

P2 (后续):
  灰度发布 (canary)
  流式 I/O 支持
  性能基准声明
  可视化依赖安全图谱
  SLA 入星级
```
