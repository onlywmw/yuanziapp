# AI 意图理解原子

> **v2 · 2026-07-19 按审计结论优化，与实现同步**
> 审计依据: design-doc-review/11-AI意图原子.md

> **定位**: 本地运行, 理解人的自然语言 → 匹配原子/工作流
> **类型归属**: 原子分类 v2「决策」类 · intelligence 为子型/标签 (非第六类)
> **原则**: 用户 query 不出设备 — system.ai 永远本地推理 (规则与 ONNX 均本地)

> **「不上云」层界 (2026-07-19 裁决)**:
>   · 用户 query 层 — system.ai 永远本地: 规则与 ONNX 均为本地推理, query 不出设备。
>   · 注册表元数据层 — M5 语义搜索的远端 embedding 属"可选增强":
>     经 EMBEDDING_API_KEY 配置启用, 无 key 自动降级本地 provider;
>     发送的是原子功能文本, 不含用户 query。
>   两层原则各自成立, 互不冲突。

---

## 一、它在工作流中的位置

```
人说的话
    │
    ▼
system.ai ──────→ 理解意图          【已实现 · 规则版, 见 base-atoms/ai/】
    │                "我想听适合下雨天的歌"
    │                → intent: play_music
    │                → params: {mood: melancholy, scene: rainy_day}
    │
    ▼
rule-engine ────→ 匹配工作流        【规划中 · 决策层, 未实现】
    │                "rainy_day + play_music → 咖啡厅音乐推荐"
    │
    ▼
music-player ───→ 播放              【规划中 · 执行层(感知层家族), 未实现】

不是替代 rule-engine — 是补在 rule-engine 前面。
rule-engine 做匹配, AI 做理解。

当前可用的真实示例链 (今日即可编排, 两端均为已实现原子):

    system.ai → system.string-match
    "把这段话里的城市名提取出来"
      → system.ai 抽出 {text, keyword}
      → system.string-match 执行匹配
    (13 个基础原子均可作为 system.ai 的下游节点)
```

## 二、原子定义

```
atom_id:   system.ai
分类:      决策类 (原子分类 v2 五类之一) · 子型标签: intelligence
描述:      本地意图理解 — 自然语言 → 结构化意图
输入:      {query: str 必填, context: object 可选}
输出:      {
             intent: str,
             params: object,
             matched_atoms: list,
             matched_workflows: list,
             confidence: float (0~1),
             source: "rules" | "onnx"
           }
运行:      三轨运行时 (见 §三), 默认零依赖规则兜底
延迟:      规则 < 1ms · ONNX < 100ms (本地推理)
```

**归并决定 (2026-07-19, 只记录于本文档, 不改动 DESIGN_ATOM_V2_CLASSIFICATION.md)**:

- system.ai 归入 v2 五类的**决策类** — "理解人想做什么"与 rule-engine 的
  "情境 → 规则匹配 → 动作决策"同属决策职责, AI 做理解、rule-engine 做匹配,
  是决策类内部的前后分工, 不开第六类。
- `intelligence` 只作子型/标签, 不进入 atom-registry-schema.json 的 type 枚举
  (本次不动 schema); v2 分类落地时按本条归并, 不产生第十一枚举值。

## 三、运行时路线 (三轨)

```
轨道 1 · 规则兜底 (默认, 已实现)
  依赖:    零依赖, 零模型
  速度:    < 1ms
  能力:    关键词匹配, 有限意图识别
  地位:    默认实现, 任何环境可用, source="rules"
  落地:    base-atoms/ai/

轨道 2 · ONNX Python provider (桌面/服务端, 可选增强)
  依赖:    onnxruntime (可选安装, 不装不影响轨道 1)
  模型:    AI_MODEL_PATH 环境变量指定本地模型路径
  回退:    未装 onnxruntime 或未设 AI_MODEL_PATH → 自动回退规则轨
  推理:    永远本地, source="onnx"
  适用:    桌面 / 服务端 Python 环境
  选型:    需中文意图分类模型 + 中文分词方案
           (distilbert 为英文体系, 不直接适用, 选型待论证)

轨道 3 · APK 侧 Java AAR (远期)
  形态:    Java 侧 onnxruntime-android AAR + Python 仅做前/后处理
  原因:    onnxruntime 含 C 扩展, Chaquopy 官方包仓库无 Android wheel
           (chaquo/chaquopy issue #216 自 2020 年开放至今,
            #1363 (2025-04) 仍确认不可装)
           → "Chaquopy 内嵌 Python → ONNX Runtime" 路线不可行, 已废弃
  模型:    随 APK assets 打包, 需哈希/签名校验
           (供应链校验属 M6 威胁模型补充项)

已删除: 方案 C (用户本地 Claude CLI) — 本质是云端 API 调用,
        违反"不上云"原则, 本版移除。
```

**默认策略**: 有 ONNX 环境走轨道 2, 否则轨道 1 兜底; 两条轨的输出契约一致,
仅 `source` 字段区分 (`rules` | `onnx`)。

## 四、意图 → 原子的映射

AI 理解意图后, 需要映射到具体的原子或工作流:

```
意图 → 现存原子/能力 (今日可用):

  search/recommend → M5 /search 语义检索 (已上线)
  create_note      → system.file-write   (13 基础原子)
  match_text       → system.string-match (13 基础原子)
  ...

意图 → 规划中原子 (感知/执行层, 未实现):

  play_music       → system.music-player  【规划中】
  check_weather    → system.weather       【规划中】
  find_place       → system.location      【规划中】
  send_message     → system.notification  【规划中】

参数提取:

  "适合下雨天的歌"
    → scene: rainy_day
    → mood: melancholy
    → action: play

  "附近有什么好吃的"
    → location: current (待 system.location 落地后获取)
    → category: restaurant
    → action: search
```

**与 M5 的分工 (2026-07-19 裁决)**: system.ai 本体只做 intent 分类 + 参数抽取;
输出中 `matched_atoms` / `matched_workflows` 的填充复用 M5 `search_functions`
(/search 端点, 已上线, 支持远端/本地双 provider) — 不另起第二套
query → 原子匹配实现。

## 五、与工作流的关系

```
方式 1: AI 直接触发工作流          【可用 — 工作流引擎已实现】
  人: "下雨天模式"
  AI: intent=activate_workflow, workflow="coffee_shop_music"
  → 直接启动工作流

方式 2: AI 作为工作流的一环        【规划中 — 依赖感知层原子与级联触发地基, 均未实现】
  location → weather → device → context-fusion
                                  ↓
                             system.ai ← "理解当前情境"
                                  ↓
                             rule-engine → music-player

方式 3: AI 推荐但不执行            【可用】
  人: "我想听歌"
  AI: "你的咖啡厅音乐推荐工作流适合现在, 要启动吗？"
  人: [确认]
  → 启动
```

## 六、模型训练/更新

```
初始模型 (仅轨道 2/3 涉及):
  预训练中文意图分类模型 (选型待论证, 见 §三轨道 2)
  覆盖 20-30 个常见意图

个性化:
  人使用越多 → 越准确
  记录: 人的 query → AI 理解 → 人的反馈 (点确认/修改/取消)
  本地微调 (不需要上传数据)

  隐私: 所有数据留在设备上
```

## 七、关键词兜底规则

模型不可用时的默认实现 (即轨道 1, 见 §三):

```
术语切割: 本节规则是 system.ai 内部的关键词映射表, 直接对原始 query
做包含匹配; 它不是 system.rule-engine — 后者输入 {situation, context},
规则存于 atom_registry 中 type=rule 的原子。两者规格不同, 勿混淆。

  "下雨天" in query          → scene=rainy_day, intent=play_music
  "咖啡厅" in query          → location=cafe
  "想听" + "歌" in query     → intent=play_music
  "天气" in query            → intent=check_weather
  "附近" + "好吃的" in query → intent=search, category=food

规则匹配率: ~60-70%
模型匹配率: ~90%+ (轨道 2/3 目标值, 待选型后实测)
```

## 八、架构

```
┌──────────────────────────────────────────────┐
│  system.ai (决策类 · intelligence 子型)        │
│                                              │
│  ┌───────────────┐   ┌────────────────────┐  │
│  │ 轨道 1 规则兜底 │   │ 轨道 2 ONNX provider│  │
│  │ 默认 · 已实现   │   │ 可选 · AI_MODEL_PATH│  │
│  │ < 1ms         │   │ < 100ms · 本地推理  │  │
│  └──────┬────────┘   └─────────┬──────────┘  │
│         │   缺省/失败自动回退 ──┘              │
│         └─────────┬───────────               │
│           ┌───────▼───────────┐              │
│           │ 意图 → 原子映射    │              │
│           │ matched_* 复用    │              │
│           │ M5 /search 检索   │              │
│           └───────────────────┘              │
└──────────────────────────────────────────────┘
轨道 3 (APK · 远期): Java onnxruntime-android AAR, Python 仅前/后处理
```

## 九、实施

```
Phase 1: 规则版 — 已落地
  · base-atoms/ai/ (core.py 暴露 handler, 引擎按目录动态加载)
  · 关键词 → 意图映射表, 零依赖零模型
  · I/O 契约按 §二 定稿, source="rules"

Phase 2: ONNX provider 接入 (桌面/服务端)
  · onnxruntime 可选依赖, AI_MODEL_PATH 环境变量
  · 缺省/加载失败自动回退规则轨
  · 中文意图模型选型 + 导出 ONNX

Phase 3: APK AAR 集成 (远期)
  · Java 侧 onnxruntime-android AAR
  · 模型随 APK 打包 + 哈希/签名校验
```

---

> **不是替代规则引擎。是补在规则引擎前面。AI 理解"人想做什么", 规则引擎决定"怎么做"。**
