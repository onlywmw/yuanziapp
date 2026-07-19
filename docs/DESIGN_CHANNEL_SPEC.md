# 通道规范

> **定位**: 原子间数据流转的完整技术规格。合并 CHANNEL_MODEL + ATOM_CONNECTION_RULES + WORKFLOW_CONNECTION_RULES + WORKFLOW_RESILIENCE
> **硬伤修复**: 映射语法、合并时序、分流路由、保存时校验、通道版本

---

## 一、通道数据结构

```json
{
  "channel_id": "ch_001",
  "type": "map",
  "source": "system.http-get",
  "target": "system.json-parse",
  "mapping": {
    "body": "$.text"
  },
  "fault": {
    "strategy": "retry",
    "max_retries": 3,
    "retry_intervals_ms": [1000, 3000, 10000],
    "on_exhausted": "abort"
  },
  "version": 1,
  "created_at": "2026-07-19T..."
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| channel_id | 是 | 工作流内唯一 |
| type | 是 | direct / map / transform / merge / split |
| source | 是 | 源原子 id |
| target | 是 | 目标原子 id |
| mapping | 视类型 | 字段映射, direct 无 |
| merge_strategy | merge 必填 | 合并策略 |
| split_rules | split 必填 | 分流规则 |
| transform_fn | transform 必填 | 转换函数标识 |
| fault | 否 | 容错策略, 默认 abort |
| version | 是 | 通道版本, 初始 1 |

---

## 二、五种通道的技术规格

### direct (直通)

```
source 的输出完整传给 target。
mapping 字段不存在。

执行:
  target_input = source_output

适用:
  source 的输出结构 ⊆ target 的输入结构
  字段名和类型完全一致
```

### map (映射)

```
将 source 输出的字段名映射到 target 输入的字段名。

mapping 语法: 目标字段名 → 源字段路径

路径格式:
  "field"           顶层字段
  "field.sub"       嵌套字段 (点号分隔)
  "$.field.sub"     JSONPath 语法 (可选, 等同于上面)
  "@.field"         源为数组时取当前元素字段
  "#.field"         源为数组时取第 0 个元素的字段

执行:
  target_input[目标字段名] = resolve(source_output, 源字段路径)

解析规则:
  1. 先试 JSONPath ($.field.sub)
  2. 回退到点号分隔 (field.sub)
  3. 路径不存在 → null (不报错, 交给容错策略)

示例:
  源输出: {"data": {"temperature": 18, "humidity": 85}}
  映射:   {"temp": "$.data.temperature", "humid": "$.data.humidity"}
  结果:   {"temp": 18, "humid": 85}
```

### merge (合并)

```
多个 source 的输出合并为一个 target 的输入。

merge_strategy 取值:

  "wait_all"    等所有源都到达 → 合并 → 传给 target
                timeout 后仍有源未到 → 容错策略处理

  "first_wins"  第一个到达的 → 立即传给 target
                (其余忽略)

  "concat"      所有源的值拼接为数组 → 传给 target
                ["源1的值", "源2的值"]

  "merge"       同名字段, 后来的覆盖先来的

  "template"    按模板字符串组合
                模板: "现在是 {weather.temp}°, {weather.condition}"

timeout_ms:
  wait_all 模式下最长等待时间, 默认 5000ms
  超时后未到达的源 → 对该源执行 fault 策略

示例:
  源1: {"temp": 18}
  源2: {"condition": "rain"}
  strategy: "merge"
  合并: {"temp": 18, "condition": "rain"}
```

### split (分流)

```
一个 source 的输出分发给多个 target。

split_rules: 目标 atom_id → 路由条件

路由条件:
  null          无条件, 所有目标收到相同数据 (默认)
  JSONPath       取源输出的某个字段值作为条件
  function       自定义函数 (作者提供的 handler)

示例:
  源输出: {"action": "play", "track": "Stan"}
  分流:
    "system.music-player": null       → 收到完整数据
    "system.notification": null       → 收到完整数据

  源输出: {"type": "text", "content": "hello"}
  分流:
    "system.file-write": {"when": "$.type == 'text'"}    → 只收文本
    "system.music-player": {"when": "$.type == 'audio'"} → 只收音频
```

### transform (转换)

```
source 输出的类型不是 target 需要的类型, 需要转换。

transform_fn: 系统内置转换函数标识

内置函数:
  "toString"    任意 → 字符串
  "toNumber"    字符串 → 数字
  "toBoolean"   字符串/数字 → 布尔
  "toJson"      字符串 → JSON 对象
  "fromJson"    JSON → 字符串
  "round(n)"    数字 → 保留 n 位小数

不支持自定义转换函数 (防止注入)。
需要复杂转换时 → 插入一个工具原子作为中转。
```

---

## 三、保存时校验

不是运行时才发现连线错误。保存工作流时就要检查。

```
校验项                       拒绝/警告    说明
──────────────────────────────────────────────────
type 不是 5 种之一             拒绝         未知通道类型
source 原子不存在              拒绝         依赖缺失
target 原子不存在              拒绝         依赖缺失
map 映射路径语法错误            拒绝         无法解析
merge 缺 merge_strategy        拒绝         merge 必须声明策略
split 目标数 < 2              拒绝         split 至少 2 个目标
循环依赖 (A→B→A)              拒绝         拓扑排序检测
类型不匹配                     警告         source 输出 ≠ target 输入
安全降级                       警告         source 安全级别 > target
merge timeout 未设              警告         默认 5000ms
```

---

## 四、通道版本

```
通道的 mapping 或 strategy 改了 → version +1。

下游工作流依赖通道时:
  锁定版本: "ch_001@v2"
  自动升级: 通道 author 声明 compatible=true → 下游自动用新版本
  手动升级: compatible=false → 下游作者收到通知, 手动确认升级

不锁版本的后果:
  张三改了映射规则 body→text 改成 body→data
  李四的工作流还在用旧规则 → text 字段为 null → 静默炸了
```

---

## 五、工作流图中的通道

```
工作流 DAG 中的连线携带完整通道定义:

{
  "workflow_id": "coffee_shop",
  "nodes": [...],
  "channels": [
    {
      "channel_id": "ch_001",
      "type": "map",
      "source": "weather",
      "target": "context-fusion",
      "mapping": {"weather_condition": "$.condition"},
      "fault": {"strategy": "fallback", "fallback_value": {"condition": "unknown"}}
    },
    {
      "channel_id": "ch_002", 
      "type": "merge",
      "source": ["context-fusion", "system.clock"],
      "target": "rule-engine",
      "merge_strategy": "merge",
      "fault": {"strategy": "abort"}
    }
  ]
}
```

---

## 六、执行引擎如何用通道

```
伪代码:

for each channel in topological_order:
    source_output = node_results[channel.source]
    
    # 1. 转换
    if channel.type == "direct":
        target_input = source_output
    elif channel.type == "map":
        target_input = apply_mapping(source_output, channel.mapping)
    elif channel.type == "merge":
        target_input = apply_merge(source_outputs, channel.merge_strategy)
    elif channel.type == "split":
        for output in apply_split(source_output, channel.split_rules):
            deliver(output, target)
        continue
    elif channel.type == "transform":
        target_input = builtin_transform(source_output, channel.transform_fn)
    
    # 2. 容错
    if target_input is ERROR:
        result = handle_fault(channel.fault, channel.source, channel.target)
        if result is ABORT:
            raise WorkflowAborted
        if result is SKIP:
            continue
        if result is FALLBACK:
            target_input = channel.fault.fallback_value
    
    # 3. 传递
    node_results[channel.target] = target_input
```

---

## 七、实施

```
P0 (立即):
  合并 4 份文档 → DESIGN_CHANNEL_SPEC.md
  通道数据结构定义 (JSON schema)
  映射路径语法规范 (点号 + JSONPath)
  合并时序语义 (wait_all/first_wins/concat/merge/template)

P1 (1-2 周):
  保存时校验 (循环/类型/安全)
  通道版本 + 锁定

P2 (后续):
  通道测试框架
  通道变更通知
```

---

> **829 行 → 1 份技术规格。五种通道都有确切的 JSON schema、解析规则、容错语义。**
