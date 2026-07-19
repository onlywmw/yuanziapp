# 从 Vane 可借鉴的

> **Vane 是什么**: 自托管 AI 搜索引擎 — 分类→研究→生成答案, 带引用来源
> **核心流程**: classify → parallel(research + widgets) → answer

---

## 可借鉴的

### 1. 分类先行

```
Vane: 
  收到问题 → 先分类: 需要搜索吗? 需要小组件吗? 怎么改写?
  → 分类结果决定后续流程

Yuanzi 可借鉴:
  system.ai 理解意图后 → 不只是匹配工作流
  → 先分类: 这是查询类? 执行类? 感知类?
  → 分类决定调度策略 (并行还是串行, 要不要缓存, 允不允许降级)
```

### 2. 并行执行

```
Vane:
  research (搜索) 和 widgets (天气/股票/计算器) 同时跑
  互不等待, 谁先完成先显示

Yuanzi:
  工作流引擎可以借鉴:
    同一拓扑层级的原子 → 并行执行
    没有依赖关系的 → 不互相等待
    当前设计已经提到了, 但 Vane 的实现更成熟
```

### 3. 小组件 = 上下文, 不是答案

```
Vane:
  Widgets (天气/股票) 提供上下文 → 帮助 LLM 更好地回答
  但 Widgets 本身不被引用

Yuanzi:
  感知原子 (location/weather/clock) = Widgets
  它们提供上下文, 不直接输出给用户
  最终输出的是决策/执行原子 (music/notification)
```

### 4. 运行模式

```
Vane:
  speed     → 快速, 跳过深度搜索
  balanced  → 日常
  quality   → 深度研究

Yuanzi 可借鉴:
  和混音台的预设类似 (调试/工作/浏览/发现)
  但 Vane 的模式影响的是执行策略, 不是视觉效果
  → 工作流引擎可加入模式: 快速(跳过非关键)/完整(全跑)
```

### 5. 自托管 + Docker

```
Vane:
  docker-compose up → 一条命令启动全部
  包含: Next.js + SearxNG + Redis

Yuanzi:
  Chaquopy 内嵌 APK = 同类的"一条命令"
  但可以再加一个 docker-compose 用于桌面/服务器部署
```

---

## 不借鉴的

```
· Next.js/React 前端 → 我们用 Android Canvas, Obsidian 风格
· LLM 作为核心 → 我们的核心是原子编排, LLM 只是其中一个原子
· 搜索作为主要功能 → 我们的搜索 (M5) 是辅助, 核心是工作流
· Meta-search (SearxNG) → 我们不是搜索引擎
```

---

## 和 Yuanzi 的本质区别

```
Vane:                        Yuanzi:
答案引擎                     能力生态
用 AI 回答问题               用原子编排能力
搜索 → 生成答案              感知 → 融合 → 决策 → 执行
用户问, 系统答               原子自动协作, 不需要人问

Vane 是"帮你搜"。
Yuanzi 是"替你跑"。
```
