# AI 意图理解原子

> **定位**: 本地运行, 理解人的自然语言 → 匹配原子/工作流
> **原则**: 不上云, 不依赖外部 API, 跑在设备上

---

## 一、它在工作流中的位置

```
人说的话
    │
    ▼
system.ai ──────→ 理解意图
    │                "我想听适合下雨天的歌"
    │                → intent: play_music
    │                → mood: melancholy
    │                → context: rainy_day
    │
    ▼
rule-engine ────→ 匹配工作流
    │                "rainy_day + play_music → 咖啡厅音乐推荐"
    │
    ▼
music-player ───→ 播放

不是替代 rule-engine — 是补在 rule-engine 前面。
rule-engine 做匹配, AI 做理解。
```

## 二、原子定义

```
atom_id:   system.ai
类型:      intelligence
描述:      本地意图理解 — 自然语言 → 结构化意图
输入:      {query: "我想听适合下雨天的歌", context: {...}}
输出:      {
             intent: "play_music",
             params: {mood: "melancholy", scene: "rainy_day"},
             confidence: 0.92,
             matched_atoms: ["system.music-player"],
             matched_workflows: ["coffee_shop_music"]
           }
运行:      Chaquopy 内嵌 Python → ONNX Runtime → 小模型
延迟:      < 200ms (本地推理)
体积:      ~50MB (模型文件)
```

## 三、模型选择

```
方案 A: ONNX + 小模型 (推荐)
  模型:    distilbert-intent-classifier (ONNX 导出)
  大小:    ~45MB
  速度:    < 100ms
  能力:    意图分类 + 实体提取
  安装:    打包在 APK 中, 或首次启动时下载

方案 B: 规则 + 关键词 (无模型)
  大小:    0MB
  速度:    < 1ms
  能力:    关键词匹配, 有限意图识别
  适用:    离线兜底 (模型下载前)

方案 C: 用户本地 Claude CLI
  大小:    0MB (复用已安装的 claude)
  速度:    ~2-5s (取决于 prompt 长度)
  能力:    完整语义理解
  问题:    Claude CLI 需要 Node.js 环境, APK 内不一定有
```

**推荐 A + B 双轨**: 有模型时用 ONNX, 模型下载前用规则兜底。

## 四、意图 → 原子的映射

AI 理解意图后, 需要映射到具体的原子或工作流:

```
意图分类:

  play_music      → system.music-player
  check_weather   → system.weather
  find_place      → system.location
  send_message    → system.notification
  create_note     → system.file-write
  recommend       → search + 工作流推荐
  ...

参数提取:

  "适合下雨天的歌"
    → scene: rainy_day
    → mood: melancholy  
    → action: play

  "附近有什么好吃的"
    → location: current (从 system.location 获取)
    → category: restaurant
    → action: search
```

## 五、与工作流的关系

```
方式 1: AI 直接触发工作流
  人: "下雨天模式"
  AI: intent=activate_workflow, workflow="coffee_shop_music"
  → 直接启动工作流

方式 2: AI 作为工作流的一环
  location → weather → device → context-fusion
                                  ↓
                             system.ai ← "理解当前情境"
                                  ↓
                             rule-engine → music-player

方式 3: AI 推荐但不执行
  人: "我想听歌"
  AI: "你的咖啡厅音乐推荐工作流适合现在, 要启动吗？"
  人: [确认]
  → 启动
```

## 六、模型训练/更新

```
初始模型:
  预训练通用意图分类
  覆盖 20-30 个常见意图

个性化:
  人使用越多 → 越准确
  记录: 人的 query → AI 理解 → 人的反馈 (点确认/修改/取消)
  本地微调 (不需要上传数据)

  隐私: 所有数据留在设备上
```

## 七、零模型兜底

模型下载完成前, 或模型加载失败时:

```
规则引擎兜底:

  "下雨天" in query          → scene=rainy_day, intent=play_music
  "咖啡厅" in query          → location=cafe
  "想听" + "歌" in query     → intent=play_music
  "天气" in query            → intent=check_weather
  "附近" + "好吃的" in query → intent=search, category=food

规则匹配率: ~60-70%
模型匹配率: ~90%+
```

## 八、架构

```
┌──────────────────────────────────────────┐
│  system.ai                                │
│                                           │
│  ┌─────────────┐    ┌──────────────────┐ │
│  │ 模型模式     │    │ 兜底模式          │ │
│  │ ONNX Runtime │    │ 规则 + 关键词     │ │
│  │ < 100ms      │    │ < 1ms            │ │
│  └──────┬───────┘    └────────┬─────────┘ │
│         │                     │           │
│         └─────────┬───────────┘           │
│                   │                       │
│           ┌───────▼───────────┐           │
│           │ 意图 → 原子映射    │           │
│           │ intent → workflow │           │
│           └───────────────────┘           │
└──────────────────────────────────────────┘
```

## 九、实施

```
Phase 1: 规则兜底 (1h)
  · 关键词 → 意图映射表
  · 20 个常见意图覆盖
  · 零依赖, 立即可用

Phase 2: ONNX 模型 (1天)
  · 选型 + 导出 ONNX
  · 打包进 APK 或首次下载
  · 意图分类 + 实体提取

Phase 3: 个性化 (1天)
  · 本地 feedback 收集
  · 模型微调 (可选)
```

---

> **不是替代规则引擎。是补在规则引擎前面。AI 理解"人想做什么", 规则引擎决定"怎么做"。**
