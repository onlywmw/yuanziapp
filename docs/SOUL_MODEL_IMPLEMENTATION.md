# 原子灵魂模型实施方案

> **状态**: `📐 design-ready`
> **依据**: ATOM_SOUL_MODEL.md
> **原则**: 不破坏现有 277 测试, 不要求 61 原子回填

---

## 一、改动清单

```
文件                              改动类型    工作量
─────────────────────────────────────────────────────
atom-registry-schema.json         加字段      5 min
migrations/011_add_soul.sql       新增迁移    5 min
registry.py                        加验证      15 min
api.py                             无改动      0
register_mcp_atoms.py              无改动      0
widgetmcp_src/.../DetailPanel.kt   加渲染      30 min
widgetmcp_src/.../MarketCard.kt    加渲染      30 min
tests/test_soul.py                 新增测试    30 min
```

---

## 二、Schema 变更

### 2.1 atom-registry-schema.json

在 `classification` 的 `properties` 中新增：

```json
"soul": {
  "type": "object",
  "description": "原子灵魂描述 — 风格/受众/基调/品质/场景/叙事",
  "properties": {
    "style": {
      "type": "array",
      "description": "风格标签, 最多3个",
      "maxItems": 3,
      "items": { "type": "string" }
    },
    "audience": {
      "type": "array",
      "description": "受众标签, 最多3个",
      "maxItems": 3,
      "items": { "type": "string" }
    },
    "mood": {
      "type": "string",
      "description": "使用基调, 单选"
    },
    "quality": {
      "type": "string",
      "description": "品质等级, 单选"
    },
    "use_case": {
      "type": "array",
      "description": "使用场景, 最多3个",
      "maxItems": 3,
      "items": { "type": "string" }
    },
    "narrative": {
      "type": "string",
      "description": "作者叙事, 10-200 字",
      "minLength": 10,
      "maxLength": 200
    }
  }
}
```

### 2.2 迁移 011

```sql
-- 011_add_soul.sql: 在 classification_json 中不强制要求 soul
-- 无 DDL 变更 (soul 存在 classification JSON 中, 不是独立列)
-- 此迁移为占位: 记录 schema 版本变更
```

`soul` 存在 `classification_json` TEXT 列中，不需要 ALTER TABLE。现有 61 原子 `soul` 为空，不报错、不崩溃。

---

## 三、验证逻辑

### 3.1 registry.py: validate_atom()

在现有 `validate_atom` 中新增 soul 校验：

```python
SOUL_STYLES = {
    "minimalist", "reliable", "professional", "elegant",
    "powerful", "lightweight", "creative", "warm",
    "bold", "playful", "geeky", "clean",
    "stable", "robust", "precise", "polished",
    "refined", "comprehensive", "fast", "lean",
    "experimental", "friendly", "hardcore",
}

SOUL_AUDIENCES = {
    "backend developer", "frontend developer", "data engineer",
    "designer", "writer", "student", "everyone", "geek",
    "devops", "researcher", "creator",
}

SOUL_MOODS = {
    "focused", "calm", "energetic", "playful",
    "serious", "inspired",
}

SOUL_QUALITIES = {
    "experimental", "functional", "polished",
    "battle-tested", "handcrafted",
}

def validate_soul(soul: dict | None) -> list[str]:
    errors = []
    if soul is None:
        return errors  # soul 可选

    for tag in soul.get("style", []):
        if tag not in SOUL_STYLES:
            errors.append(f"soul.style: unknown tag '{tag}'")
    if len(soul.get("style", [])) > 3:
        errors.append("soul.style: max 3 tags")

    for tag in soul.get("audience", []):
        if tag not in SOUL_AUDIENCES:
            errors.append(f"soul.audience: unknown tag '{tag}'")
    if len(soul.get("audience", [])) > 3:
        errors.append("soul.audience: max 3 tags")

    if soul.get("mood") and soul["mood"] not in SOUL_MOODS:
        errors.append(f"soul.mood: unknown value '{soul['mood']}'")

    if soul.get("quality") and soul["quality"] not in SOUL_QUALITIES:
        errors.append(f"soul.quality: unknown value '{soul['quality']}'")

    narrative = soul.get("narrative", "")
    if narrative and (len(narrative) < 10 or len(narrative) > 200):
        errors.append("soul.narrative: must be 10-200 characters")

    return errors
```

### 3.2 标签池可扩展

`SOUL_STYLES` 等集合定义为常量，新增标签只需加一行。未来用户可提议新标签。

---

## 四、API 响应

### 4.1 原子详情返回 soul

```json
GET /atoms/mcp.postgres

{
  "atom_id": "mcp.postgres",
  "name": "Postgres",
  "classification": {
    "category": "Database",
    "soul": {
      "style": ["minimalist", "reliable", "professional"],
      "audience": ["backend developer", "data engineer"],
      "mood": "focused",
      "quality": "polished",
      "use_case": ["daily work", "production"],
      "narrative": "写了十年 SQL 的人, 把最趁手的工具分享出来"
    }
  }
}
```

无改动: API 读 `classification_json` → 自动包含 soul。

### 4.2 搜索增强

```
POST /search
{
  "query": "简洁可靠的数据库",
  "soul_match": true    ← 新增: 启用灵魂匹配
}

搜索权重:
  功能匹配 (purpose.functions)    × 0.5
  灵魂匹配 (soul.style + audience) × 0.3
  叙事匹配 (soul.narrative)       × 0.2
```

---

## 五、UI 渲染

### 5.1 DetailPanel 新增 Soul 卡片

```
┌──────────────────────────────────────┐
│  mcp.postgres                        │
│  PostgreSQL 数据库操作               │
│                                      │
│  ── 风格 ────────────────           │
│  [极简] [可靠] [专业]               │  ← 彩色标签, 小圆角
│                                      │
│  ── 适合 ────────────────           │
│  后端开发 · 数据工程师               │
│                                      │
│  ── 感觉 ────────────────           │
│  🎯 专注                            │
│                                      │
│  ── 品质 ────────────────           │
│  ✨ 打磨过                           │
│                                      │
│  ── 作者的话 ────────────           │
│  "写了十年 SQL 的人,                │  ← 斜体, 引号
│   把最趁手的工具分享出来"            │
│                                      │
│  ── 作者 ────────────────           │
│  张三 · MIT License                 │
└──────────────────────────────────────┘
```

### 5.2 市场卡片新增风格标签

```
┌──────────────────────────────┐
│ ⭐ 4.7                       │
│ mcp.postgres                 │
│ PostgreSQL 数据库操作         │
│ [极简] [可靠] [专业]         │  ← 风格标签
│ 作者: 张三 · 128 评价        │
│ "写了十年 SQL 的人..."       │  ← 叙事截断一行
│ [安装] [详情]                │
└──────────────────────────────┘
```

---

## 六、向后兼容

```
现有 61 原子:
  classification.soul = null (或 {})
  → API 返回: "soul": null
  → UI 不渲染灵魂卡片 (不影响现有展示)
  → 搜索: soul_match=false → 纯功能搜索 (和现在一样)

新原子:
  作者填写 soul → 正常展示
  作者不填 soul → 和现有原子一样, 不报错

无迁移成本。0 破坏。
```

---

## 七、测试

```python
# tests/test_soul.py

def test_soul_optional():
    """soul 为空时不报错"""
    atom = valid_atom()
    atom["classification"]["soul"] = None
    errors = validate_atom(atom, schema)
    assert "soul" not in str(errors)

def test_soul_max_3_styles():
    """风格标签最多 3 个"""
    atom = valid_atom()
    atom["classification"]["soul"] = {"style": ["a", "b", "c", "d"]}
    errors = validate_atom(atom, schema)
    assert any("max 3" in e for e in errors)

def test_soul_narrative_length():
    """叙事 10-200 字"""
    atom = valid_atom()
    atom["classification"]["soul"] = {"narrative": "短"}
    errors = validate_atom(atom, schema)
    assert any("10-200" in e for e in errors)

def test_soul_valid_tags():
    """合法标签通过"""
    atom = valid_atom()
    atom["classification"]["soul"] = {
        "style": ["minimalist"],
        "audience": ["backend developer"],
        "mood": "focused",
        "quality": "polished",
        "narrative": "这是一个测试原子, 用来验证灵魂模型"
    }
    errors = validate_atom(atom, schema)
    assert len(errors) == 0
```

---

## 八、实施顺序

```
步骤 1: schema 加 soul 定义          (5 min, 零风险)
步骤 2: 迁移 011 (占位)              (5 min, 零风险)  
步骤 3: registry.py 加验证逻辑       (15 min, 零风险 — soul 可选)
步骤 4: 测试                          (30 min)
步骤 5: UI 加渲染                    (1h, APK 端)

总工作量: ~2 小时
破坏性: 零 (soul 可选, 不影响现有数据和测试)
```

---

> **灵魂字段是增量。现有系统完全不受影响。新原子多了六个让人类产生共鸣的字段。**
