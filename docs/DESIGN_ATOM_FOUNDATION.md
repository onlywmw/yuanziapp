# 原子基座夯实

> **定位**: 原子体系的"硬规范"——生命周期、I/O Schema、版本语义、依赖约束、安全分级、测试分层
> **原则**: 每一个决策都有理由，每一个规范都有验证方式

---

## 一、原子生命周期

```
                    ┌─────────┐
                    │  draft  │  ← 作者在写, 不可见
                    └────┬────┘
                         │ submit
                    ┌────▼────┐
                    │ review  │  ← Audit 审查中
                    └────┬────┘
                    ┌────┴────┐
                    │registered│ ← 正常状态, 可见
                    └────┬────┘
               ┌────────┼────────┐
          ┌────▼───┐┌───▼────┐┌──▼──────────┐
          │running ││offline ││ deprecated   │ ← 作者标记
          └────┬───┘└───┬────┘└──────────────┘
               │        │
          ┌────▼───┐┌───▼────┐
          │retired ││deleted  │  ← 终态: 不可恢复
          └────────┘└─────────┘

每个状态转换有触发条件和记录:
  draft→review:    作者提交, 填写完整 soul + I/O schema
  review→registered: Audit 通过, 签名生成
  registered→running: 首次探测成功
  running→offline:   连续 3 次探测失败
  registered→deprecated: 作者标记 (有新版本替代)
  deprecated→retired:   3 个月无使用 → 自动退役
  *→deleted: 作者或 Audit 删除 (基础原子不可)
```

## 二、I/O Schema 标准

每个原子的 `/meta` 端点必须返回:

```json
{
  "atom_id": "system.weather",
  "type": "sensor",
  "io": {
    "input": {
      "type": "object",
      "properties": {
        "location": {
          "type": "string",
          "description": "城市名或经纬度",
          "required": false,
          "default": "current"
        }
      }
    },
    "output": {
      "type": "object",
      "properties": {
        "condition": {"type": "string", "enum": ["sunny","cloudy","rain","snow","unknown"]},
        "temperature": {"type": "number", "unit": "celsius"},
        "humidity": {"type": "number", "minimum": 0, "maximum": 100}
      },
      "required": ["condition", "temperature"]
    }
  },
  "errors": {
    "TIMEOUT": "外部 API 超时, 请用 fallback 容错",
    "INVALID_LOCATION": "无法解析位置"
  }
}
```

### 约束

```
1. 所有原子必须声明 I/O schema (注册时验证)
2. schema 用 JSON Schema 格式
3. 错误类型必须枚举 (下游容错策略需要知道错误类型)
4. input.default/required 决定工作流连线时的参数来源
   - required=true 且无 default → 必须由上游原子提供或人工输入
   - required=false 且有 default → 上游不提供时用默认值
5. schema 变更:
   - 新增可选字段 → patch bump
   - 新增必填字段 → minor bump (下游可能需要更新)
   - 删除/改名字段 → major bump (破坏性)
```

## 三、版本语义

```
semver: MAJOR.MINOR.PATCH

MAJOR bump (x.0.0):
  · I/O schema 删除或重命名字段
  · 架构类型变更 (sensor→actuator)
  · 不再支持旧输入格式

MINOR bump (1.x.0):
  · I/O schema 新增必填字段
  · 新增功能函数
  · 性能提升但结果不变

PATCH bump (1.0.x):
  · Bug 修复
  · I/O schema 新增可选字段
  · 文档更新
  · soul 字段修改

自动判断:
  注册新版本时, 系统对比新旧 I/O schema:
    · required 字段减少 → MAJOR
    · required 字段增加 → MINOR
    · 仅 optional 变化 → PATCH
  作者可手动升级 (系统建议不可降级)
```

## 四、依赖约束

```
声明格式 (在 architecture.dependencies 中):

基础原子:
  dependencies: []   ← 不可依赖任何原子 (地基不能建在墙上)

注册原子:
  dependencies: [
    "system.http-get@^1.0",    ← 依赖基础原子 http-get, >=1.0 <2.0
    "mcp.postgres@~1.2.0"      ← 依赖注册原子 postgres, >=1.2.0 <1.3.0
  ]

版本约束语法:
  @^1.2.3  兼容版本 (>=1.2.3 <2.0.0)
  @~1.2.3  近似版本 (>=1.2.3 <1.3.0)
  @1.2.3   精确版本
  @*       任意版本
  (无)     任意版本 (默认)

解析规则:
  1. 递归解析所有依赖
  2. 检测循环 → 注册被拒
  3. 检测版本冲突 (A 要 B@^1, C 要 B@^2) → 警告, 不阻断
  4. 缺失依赖 → 注册被拒
```

## 五、安全分级

```
每个原子声明安全级别 (compliance.security_level):

L0 public      无敏感操作, 结果可公开       math-calc, string-split, date-time
L1 internal    可读取本地数据                file-read, location, weather
L2 sensitive   可写入/可联网/可感知外设      file-write, http-get, camera, device
L3 privileged  可加密/解密/访问密钥          encrypt-aes, decrypt-aes, hash-digest
L4 critical    可执行系统级操作              file-dir, rule-engine, notification

原子类型 → 最低安全级别:
  tool:     按具体功能 (file-read=L1, math-calc=L0)
  sensor:   最低 L1 (采集数据)
  fusion:   最低 L1 (处理多源数据)
  rule:     最低 L2 (做出决策)
  actuator: 最低 L2 (改变状态)

交叉检查:
  · L4 原子依赖的原子必须 ≥ L3
  · L3 原子依赖的原子必须 ≥ L2
  · L2 原子依赖的原子必须 ≥ L1
  · 不允许 L4 依赖 L0 (安全降级)
```

## 六、测试分层

```
Smoke (每个原子必须):
  · happy path: 正常输入 → success
  · missing required: 缺必填 → error
  · invalid type: 错类型 → error
  · output schema: 输出格式符合声明

Contract (每个原子必须):
  · I/O schema 匹配 /meta 声明
  · 错误类型匹配声明
  · 版本号匹配 semver

Unit (按原子类型):
  tool:      每种输入组合 → 验证输出正确性
  sensor:    mock 外部数据源 → 验证采集逻辑
  fusion:    每种输入组合 → 验证融合结果
  rule:      每种规则 → 验证匹配/不匹配
  actuator:  mock 执行结果 → 验证副作用

Integration (依赖型):
  · 依赖链路: A → B → C 全链路
  · 版本兼容: 新版本不破坏下游

E2E (关键路径):
  · 感知→融合→决策→执行 全链路
  · 容错: fallback/skip/timeout/retry
```

## 七、完整度分级

```
原子在市场/图谱中的完整度信号:

minimal (★☆☆☆☆):
  · atom_id + name + type
  · purpose.summary
  · 基本信息够了, 但缺细节

functional (★★★☆☆):
  + I/O schema 完整
  + smoke 测试通过
  + 至少一个 example

complete (★★★★☆):
  + soul 字段完整 (叙事+风格+受众)
  + contract 测试通过
  + 评分 ≥ 10

exceptional (★★★★★):
  + 作者认证
  + 区块链公证
  + 评分 ≥ 50, 平均 ≥ 4.5
  + 被工作流引用 ≥ 5 次

完整度自动计算, 在原子详情面板显示星级。
```

## 八、需要补齐的

```
优先级 P0 (影响注册):
  ⬜ I/O Schema 标准化 → atom-registry-schema.json 加 io 字段
  ⬜ 注册时验证 I/O schema → validate_atom() 加 io 校验
  ⬜ /meta 端点规范 → 所有原子 server.py 统一返回 io 字段

优先级 P1 (影响质量):
  ⬜ 版本语义规则 → registry.py 加版本建议
  ⬜ 测试分层规范 → SMOKE_TEST_SPEC 更新
  ⬜ 安全分级 → compliance.security_level 必填

优先级 P2 (影响体验):
  ⬜ 完整度星级 → 市场/图谱展示
  ⬜ 依赖版本约束 → architecture.dependencies 支持@语法
```

---

> **原子体系从"能用"到"可靠"。每个规范都有验证方式, 每个规则都有检查代码。**
