# "灵魂与可见性"拆解执行方案

> **决策**: 删除"灵魂"这个概念。内容拆到它该去的地方。
> **执行**: 3 步, 0 新增内容, 只搬家。

---

## 操作清单

### 步骤 1: 删除

```
删除: docs/DESIGN_SOUL_VISIBILITY.md
```

### 步骤 2: 字段移入原子体系

在 `docs/DESIGN_ATOM_FOUNDATION_V2.md` 的 "I/O Schema" 之后新增一节:

```
## 分类扩展字段

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

校验规则:
  - style/audience/use_case 超过上限 → 拒绝注册
  - narrative 和 description 完全一致 → 警告
  - narrative 含明显占位词 (test/测试/123/todo) → 警告
  - quality=handcrafted → Audit 审核
  - quality=experimental 且 use_case=production → 冲突警告

所有字段可选, 不填不影响注册。
```

### 步骤 3: 浮现规则移入图谱引擎

在 `docs/DESIGN_GRAPH_ENGINE.md` 的 "Renderer" 之后新增一节:

```
## 节点可见性规则

图谱只渲染符合当前视角的节点。可见性由三个因素决定:

1. 原子类型:
   - system.* → 永不渲染
   - mcp.* (管道) → 混音台管道端可见, 作品端不可见
   - 终端原子 → 混音台作品端可见, 管道端不可见

2. 混音台位置:
   - 管道端: 只渲染管道原子
   - 作品端: 只渲染终端原子
   - 中间: 全部渲染

3. 节点大小:
   - 有 classification 扩展字段的原子 → 正常大小
   - 没有的 → 缩小节点
   - 社区评分 ≥ 10 且 ≥ 4.0 的 → 略大

  节点大小 = 基础大小 × 分类系数

Store 中维护一个 visibleNodes 列表,
Renderer 只绘制 visibleNodes 内的节点。
```

---

## 文件变更

```
删:  docs/DESIGN_SOUL_VISIBILITY.md
改:  docs/DESIGN_ATOM_FOUNDATION_V2.md  (+分类扩展字段)
改:  docs/DESIGN_GRAPH_ENGINE.md        (+节点可见性规则)
改:  docs/ARCHITECTURE_OVERVIEW.md      (-灵魂与可见性行)
```

---

## 概念清理

```
删除的概念:
  ❌ "灵魂" (soul)
  ❌ "灵魂模型"
  ❌ "浮现引擎"
  ❌ "freshness 衰减"
  ❌ "作者信誉 boost"

保留的内容, 换个地方:
  ✅ 风格/受众/基调/品质/场景/叙事  → 原子体系的 classification 扩展
  ✅ 节点可见性                      → 图谱引擎的渲染规则
  ✅ 字段校验                        → 原子注册的校验规则
```
