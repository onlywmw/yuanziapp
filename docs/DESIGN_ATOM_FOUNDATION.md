# 原子基座夯实

> **定位**: 原子体系的 7 项硬规范
> **原则**: 每一项都有解释、有示例、有验证方式

---

## 1. 生命周期

原子从生到死，经过 7 个状态。每次转换有触发条件和审计记录。

```
draft         作者在写, 别人看不到。像草稿箱。
    ↓ submit
review        Audit 审查中。检查 I/O schema、soul、安全级别。
    ↓ approve
registered    正常状态, 大家能用。图谱上可见。
    ↓ probe_ok
running       实际在运行。探针确认过可达。
    ↓ probe_fail ×3
offline       暂时不可用。网络断了、API 挂了。不是删了, 是暂时。
    ↓ probe_ok
running       恢复了, 自动变回。

deprecated    作者说"别用了, 有新版替代"。还能用, 但推荐升级。
    ↓ 3个月无使用
retired       自动退役。不再出现在市场, 但历史数据保留。

deleted       作者或 Audit 删除。基础原子不可删除。
```

### 为什么需要

- `draft` 让作者可以慢慢填 soul 和 schema，不用发布半成品
- `offline` 和 `deleted` 是不同的——offline 是暂时的, 删了是永久的
- `deprecated` 给下游用户一个升级窗口

### 验证方式

```
每次状态转换 → _audit() 写审计日志
非法转换 → set_atom_status() 拒绝, 返回 invalid_transition
```

---

## 2. I/O Schema

每个原子的 `/meta` 端点必须返回标准 JSON Schema。说清楚：我吃什么、我吐什么、我会出什么错。

```
system.weather 的 /meta 返回:

{
  "io": {
    "input": {
      "location": {
        "type": "string",
        "description": "城市名",
        "required": false,
        "default": "current"
      }
    },
    "output": {
      "condition": {
        "type": "string",
        "enum": ["sunny","cloudy","rain","snow","unknown"]
      },
      "temperature": {
        "type": "number",
        "unit": "celsius"
      }
    },
    "errors": {
      "TIMEOUT": "外部 API 超时",
      "INVALID_LOCATION": "位置无法解析"
    }
  }
}
```

### 为什么需要

```
工作流连线时, 系统自动检查:

  math-calc 输出: {result: number}
  http-get 输入:  {url: string}

  number ≠ string → 类型不匹配 → 红线提示

不是靠人记住"这个原子吃什么"。
系统自动检查, 连线时立刻知道对不对。

容错需要错误类型:
  错误是 TIMEOUT (等一下可能好) → 用 retry
  错误是 INVALID (永远不行) → 用 skip 或 abort
```

### 验证方式

```
注册时: validate_atom() 检查 io 字段存在且符合 JSON Schema 格式
运行时: 每个 handler 调用前用 jsonschema.validate(input, schema)
```

---

## 3. 版本语义

升级原子时，版本号怎么变——有规则，不是乱写。

```
PATCH (1.0.0 → 1.0.1):
  · bug 修复
  · 加可选字段 (不破坏下游)
  · 改 soul 描述

MINOR (1.0.1 → 1.1.0):
  · 加新功能
  · 加必填字段 (下游需要更新但不是破坏性)

MAJOR (1.1.0 → 2.0.0):
  · 删字段或改字段名
  · 改输出类型 (number → string)
  · 不再支持旧输入格式

系统自动对比新旧 I/O schema:
  旧输出 {result: number}
  新输出 {result: string}
  → "检测到输出类型变化, 建议 MAJOR bump"
  → 作者确认或手动修改
```

### 为什么需要

```
张三的原子被李四的工作流依赖:
  李四声明了 "system.weather@^1.0" (兼容 1.x)

  张三修了个 bug → 1.0.1 → 李四自动用新版本 ✅
  张三加了功能  → 1.1.0 → 李四自动用新版本 ✅
  张三改了输出格式 → 如果用 2.0.0 → 李四的不自动升 ✅
       → 如果张三不升 MAJOR, 只是 1.1.1 → 李四的工作流炸了 ❌
```

### 验证方式

```
submit_atom 时如果 version 已存在:
  系统对比新旧 I/O schema → 自动建议 bump 级别
  作者可手动升级 (不可降级)
```

---

## 4. 依赖约束

原子可以依赖别的原子。用 `@版本` 语法声明版本约束。

```
声明:
  dependencies: [
    "system.http-get@^1.0",      ← 1.0 ~ 2.0 都行
    "mcp.postgres@~1.2.0"        ← 1.2.0 ~ 1.3.0 都行
  ]

语法:
  @^1.2.3   兼容 (≥1.2.3, <2.0.0)
  @~1.2.3   近似 (≥1.2.3, <1.3.0)
  @1.2.3    精确
  @*        任意
  (无)      任意
```

### 规则

```
1. 基础原子 (system.*): 不能依赖任何原子
     地基不能建在墙上 — 依赖的基础原子如果坏了, 所有下游全炸

2. 注册原子: 可以依赖基础原子, 也可以依赖别的注册原子

3. 不能循环: A → B → A → 注册被拒

4. 安全不降级:
     L4 (加密) 依赖 L2 (网络请求)
     → "加密原子的输入来自较低安全级别的原子"
     → 警告, 不阻断, 但作者要知道
```

### 验证方式

```
注册时: resolve_dependencies() 递归解析
  检测循环 → 拒绝注册
  检测缺失 → 列出, 警告
  检测安全降级 → 警告
```

---

## 5. 安全分级

每个原子有个安全标签，L0 到 L4。

```
L0 公开     数学计算、字符串处理    无所谓, 结果可公开
L1 内部     读文件、读位置、读天气  能看到你的数据
L2 敏感     写文件、发网络、摄像头   能改变状态
L3 特权     加密、解密、哈希        能碰密钥
L4 关键     规则引擎、通知           能做重要决定

原子类型 → 最低级别:
  tool:      看功能 (file-read=L1, math-calc=L0)
  sensor:    ≥L1 (它在采集你的数据)
  fusion:    ≥L1
  rule:      ≥L2 (它在做决策)
  actuator:  ≥L2 (它在改变状态)
```

### 为什么需要

```
工作流中的安全降级检测:

  http-get (L2) ──→ encrypt-aes (L3) ──→ file-write (L2)

  系统检查原料来源:
    encrypt-aes 是 L3, 但它的输入来自 L2 的 http-get
    → "加密原子接收来自低安全级别的数据, 请注意"
    → 不阻断, 但警告

  正确做法:
    中间加一个校验原子 (L2) 来验证 http-get 的输出
    http-get (L2) → validate-input (L2) → encrypt-aes (L3)
```

---

## 6. 测试分层

不同原子需要不同深度的测试。

```
Smoke (全部都要, 注册时必须):
  · 正常输入 → success
  · 缺必填字段 → error
  · 错误类型 → error, message 匹配声明
  · 输出格式 → 字段名、类型与 /meta 声明一致

Contract (全部都要):
  · /meta 返回的 io schema 合法
  · handler 的输出真的符合 io schema
  · 声明了错误类型, handler 确实会返回这些错误

Unit (按类型):
  工具:     10+ 种输入组合 → 输出正确
  感知:     mock GPS/摄像头/蓝牙 → 采集逻辑正确
  融合:     缺 1/2/3 个输入 → 融合结果合理
  规则:     匹配/不匹配/无规则 → 决策正确
  执行:     mock 实际执行 → 副作用正确

Integration (有依赖的):
  · A → B → C 全链路
  · 新版本不破坏下游

E2E (关键路径):
  · 感知→融合→决策→执行 全自动
  · fallback: 上游失败 → 真的走了降级
  · retry: 失败 → 真的重试了 → 真的恢复了
```

### 验证方式

```
注册时: Smoke + Contract 必须通过 (CI 运行)
发布前: Unit + Integration 推荐通过
关键路径: E2E 定期运行 (每周/每次部署)
```

---

## 7. 完整度星级

不是所有原子都一个等级。星级自动计算，倒逼作者把原子做好。

```
★☆☆☆☆ minimal
  有 atom_id + name + type + purpose.summary
  → 基本信息够了, 但人家不知道你输入输出是什么

★★★☆☆ functional
  + I/O schema 完整
  + smoke 测试通过
  + 至少一个使用示例
  → 能用了

★★★★☆ complete
  + soul 完整 (有叙事+风格+受众)
  + contract 测试通过
  + 社区评分 ≥ 10 人
  → 好用了

★★★★★ exceptional
  + 作者认证
  + 区块链公证
  + 评分 ≥ 50 人, 平均 ≥ 4.5
  + 被 5 个以上工作流引用
  → 精品
```

### 为什么需要

```
市场排序: ★★★★★ 排上面, ★☆☆☆☆ 排下面
图谱展示: ★★★★☆ 以上首页可见
工作流推荐: 优先推荐高星级的

作者不填 soul → 永远 ★☆☆☆☆ → 没人看到
填了 soul → ★★★★☆ → 首页可见 → 有人用 → ★★★★★

不是惩罚, 是激励。
```

### 验证方式

```
每次原子更新 → 重新计算星级
API 返回原子的 star_level 字段
GET /atoms?star_level=4 可过滤
```

---

## 实施优先级

```
P0 (影响注册):
  I/O Schema 标准化     → atom-registry-schema.json + io 字段
  注册时验证 I/O        → validate_atom() + io 校验
  /meta 端点规范        → 所有 server.py 统一返回 io

P1 (影响质量):
  版本语义自动建议      → registry.py bump_suggestion()
  测试分层规范          → SMOKE_TEST_SPEC 更新
  安全分级必填          → compliance.security_level

P2 (影响体验):
  完整度星级            → 市场/图谱展示
  依赖版本约束          → architecture.dependencies
```
