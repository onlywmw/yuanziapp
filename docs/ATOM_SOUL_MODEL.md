# 原子灵魂模型

> **核心**: 原子不只是功能清单。它是一个商品、一个服务、一个作品。
> **目标**: 让数据采集能切中人的心坎——风格匹配、喜好共鸣、人找得到属于自己的原子。

---

## 一、原子不止是工具

```
技术视角 (冷):                    人的视角 (暖):
─────────────                    ─────────────
mcp.postgres                     "一个稳如老狗的数据库工具"
7 个功能                          "适合后端开发, 生产级品质"
分类: Database                    "简洁、可靠、不花哨"
作者: 张三                         "来自一个写了十年 SQL 的人"

← M1-M6 已经做好了               ← 缺少这一层
```

**终端原子**——直接面向用户的原子——它可能是一个商品、一个服务、一个作品。人对它有审美偏好、情感倾向、风格判断。

---

## 二、灵魂字段

在当前 schema 的 `classification` 下新增 `soul` 子对象：

```json
{
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

### 2.1 风格标签 (style)

```
一个人面对两个功能完全一样的原子, 怎么选？

  原子 A: minimalist, clean, fast
  原子 B: feature-rich, configurable, powerful

风格让人找到"对味"的那个。

风格标签池 (开放, 不限制):
  极简 / 简约       - minimalist, clean
  可靠 / 稳重       - reliable, stable, robust
  专业 / 严谨       - professional, precise
  优雅 / 精致       - elegant, polished, refined
  强大 / 全面       - powerful, comprehensive
  轻量 / 快速       - lightweight, fast, lean
  创意 / 实验       - creative, experimental, bold
  温馨 / 亲和       - warm, friendly, playful
  硬核 / 极客       - hardcore, geeky
```

### 2.2 受众标签 (audience)

```
这个原子是为谁做的？

  后端开发者
  前端开发者
  数据工程师
  设计师
  作家 / 内容创作者
  学生 / 初学者
  所有人
  极客 / 爱好者
```

### 2.3 基调 (mood)

```
用这个原子的时候, 人是什么感觉？

  focused     专注
  calm        平静
  energetic   精力充沛
  playful     轻松愉快
  serious     严肃认真
  inspired    受启发
```

### 2.4 品质 (quality)

```
这个原子做到什么程度了？

  experimental    实验性的, 可能会改
  functional      能用的
  polished        打磨过的, 细节到位
  battle-tested   久经考验
  handcrafted     匠心手作
```

### 2.5 使用场景 (use_case)

```
什么情况下用这个原子？

  daily work      日常工作
  production      生产环境
  learning        学习
  prototyping     原型开发
  creative        创意项目
  emergency       紧急救火
```

### 2.6 叙事 (narrative)

```
一句话, 人写的, 不是 AI 生成的。

  好: "写了十年 SQL 的人, 把最趁手的工具分享出来"
      "从自己的项目中抽出来的, 用了三年没问题"
      "为女儿做的第一个小程序"
  差: "这是一个数据库工具"
      "PostgreSQL database operations"

叙事让人和作者产生连接。
```

---

## 三、为什么这层很重要

### 3.1 匹配

```
传统搜索: "我需要一个数据库工具" → 返回 7 个数据库原子, 不知道选哪个

灵魂搜索: "我需要一个数据库工具, 风格简洁, 适合生产环境"
         → 返回 mcp.postgres (风格: minimalist + reliable + polished)
         → 附上叙事: "写了十年 SQL 的人..."
         → 人看到: 这个对味, 用这个
```

### 3.2 情感连接

```
人看到一个原子:

  只有功能描述:
    "PostgreSQL 数据库操作, 7 个功能"
    → "嗯, 一个工具"

  有灵魂描述:
    "一个稳如老狗的数据库工具, 适合后端开发, 生产级品质"
    风格: 极简/可靠/专业
    叙事: "写了十年 SQL 的人, 把最趁手的工具分享出来"
    → "这个人懂我, 用他做的工具我放心"
```

### 3.3 推荐

```
基于灵魂的推荐:

  你喜欢风格极简、基调专注、品质打磨过的原子
    → 推荐同风格的原子
    → 即使功能类别不同

  你收藏了很多"handcrafted"品质的原子
    → 推荐其他手作原子
    → 即使作者不同
```

---

## 四、数据采集

### 4.1 谁填写

```
基础原子: system 预填
注册原子: 作者在注册时填写 (可选, 但推荐)
终端原子 (商品/服务/作品): 作者必须填写
```

### 4.2 采集方式

```
注册表单中, 每个灵魂字段用卡片式选择器:

  ┌──────────────────────────────┐
  │  这个原子是什么风格？         │
  │                              │
  │  [极简] [可靠] [优雅] [强大] │  ← 多选, 最多 3 个
  │  [轻量] [创意] [温馨] [硬核] │
  │                              │
  │  谁最适合用这个原子？         │
  │                              │
  │  [后端开发] [数据工程]       │  ← 多选, 最多 3 个
  │  [所有人] [学生] [极客]      │
  │                              │
  │  用这个原子感觉如何？         │
  │  [专注] [平静] [精力充沛]    │  ← 单选
  │                              │
  │  做得怎么样了？              │
  │  [实验] [能用] [打磨过]      │  ← 单选
  │  [久经考验] [匠心手作]       │
  │                              │
  │  一句话介绍 (人写的)         │
  │  ┌──────────────────────┐   │
  │  │                      │   │  ← 作者自己写
  │  └──────────────────────┘   │
  │                              │
  │  主要用于什么场景？         │
  │  [日常工作] [生产环境]       │  ← 多选
  │  [学习] [创意] [紧急救火]    │
  └──────────────────────────────┘
```

### 4.3 验证

```
风格标签: 每人最多选 3 个 (防止标签膨胀)
受众标签: 每人最多选 3 个
叙事: 10-200 字, 人工审核或社区举报 (防止广告)
```

---

## 五、Schema 扩展

```json
{
  "classification": {
    "soul": {
      "style": ["string"],         // 风格标签, 最多3个
      "audience": ["string"],      // 受众标签, 最多3个
      "mood": "string",            // 基调, 单选
      "quality": "string",         // 品质, 单选
      "use_case": ["string"],      // 使用场景, 最多3个
      "narrative": "string"        // 作者叙事, 10-200字
    }
  }
}
```

`soul` 对象全局可选, 不破坏现有 277 测试和 61 原子。

---

## 六、对搜索和推荐的影响

```
M5 语义搜索 (已有):
  "数据库查询" → 匹配 purpose.functions

M5 + Soul (增强):
  "一个简洁可靠的数据库工具, 适合生产环境"
    → 匹配 purpose.functions (数据库)
    → 匹配 soul.style (简洁, 可靠)
    → 匹配 soul.quality (生产级)
    → 匹配 soul.audience (后端开发)
    → 排序加权: soul 匹配 > 纯功能匹配

推荐 (新):
  "喜欢 mcp.postgres 的人还喜欢..."
    → 同 soul.style + 同 soul.mood → 推荐
    → 同 soul.quality (handcrafted) → 推荐
    → 同作者 → 推荐
```

---

> **功能描述让人找到"能用"的原子。灵魂描述让人找到"属于自己的"原子。**
> **原子是工具, 也是作品。人通过这些作品, 连接到了另一个人。**
