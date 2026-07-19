# 工作流容错系统设计

> **状态**: `📐 design-ready`
> **问题**: 工作流中一个环节失败, 整个链不能停
> **方案**: 每根连线声明容错策略, 执行引擎按策略处理, 图谱实时反映状态

---

## 一、问题场景

```
咖啡厅工作流:

  location ──→ GPS 超时 (在地下室)
  weather  ──→ API 正常
  camera   ──→ 没识别到咖啡 (角度不对)
  device   ──→ 蓝牙正常
  clock    ──→ 正常
       │
       ▼
  context-fusion → 输入不完整但够用
       │
       ▼
  rule-engine → 匹配到规则
       │
       ▼
  music-player → 找不到《Stan》

期望: 人还是听到了歌。三个环节失败, 工作流没停。
```

## 二、五种容错策略

```
retry       重试 N 次, 间隔递增          网络抖动、API 短暂不可用
fallback    用预设默认值替代              传感器偶发失败、缓存兜底
skip        跳过该节点, 继续下游          非关键输入, 不影响整体结果
timeout     等待 X 秒, 超时就降级         外部 API 慢, 不能无限等
abort       出错立即停止整个工作流        关键路径 (支付、安全、认证)
```

### retry

```
配置:
  max_retries: 3
  intervals: [1s, 3s, 10s]   ← 递增间隔, 给外部服务恢复时间

行为:
  第 1 次失败 → 等 1s → 重试
  第 2 次失败 → 等 3s → 重试
  第 3 次失败 → 等 10s → 重试
  全部失败 → 按该连线的降级策略处理 (fallback/skip/abort)

适用: weather API 偶尔超时, 重试一次就好了
```

### fallback

```
配置:
  fallback_value: {...}       ← 预设的默认值

行为:
  原子执行失败 → 不进错误状态 → 直接使用 fallback_value

示例:
  location 失败 → fallback: {place: "上次位置", type: "cafe"}
  weather 失败 → fallback: {condition: "unknown", temp: 20}
  camera 失败  → 不适用 fallback (视觉数据不可捏造), 应选 skip

适用: 传感器、缓存数据、上次的值
```

### skip

```
配置: 无

行为:
  原子执行失败 → 标记为 skipped → 下游继续执行
  下游收到的输入比预期少一个, 但不影响整体

示例:
  camera 失败 → skip → fusion 用 4 个输入 (缺 camera) 仍能判断情境
  music-player 找不到某首歌 → skip → 播下一首

适用: 非关键输入, 缺了不碍事
```

### timeout

```
配置:
  timeout_seconds: N

行为:
  原子执行超过 N 秒 → 中断 → 按降级处理

示例:
  weather API 设置 timeout=3s → 3 秒内没响应 → fallback 用缓存
  防止一个慢 API 拖死整个工作流

适用: 外部 API 调用, 必须限时
```

### abort

```
配置: 无

行为:
  原子执行失败 → 整个工作流立即停止 → 标记为 FAILED
  下游不再执行

示例:
  支付环节 → abort → 钱扣不了, 后续不能走
  安全认证 → abort → 认证失败, 不能继续
  数据库写入 → abort → 数据丢了, 不能继续

适用: 关键路径, 失败意味着后续无意义
```

## 三、通道模型扩展

每根连线新增 `fault` 字段:

```json
{
  "channel_id": "c1",
  "type": "map",
  "source": "system.weather",
  "target": "system.context-fusion",
  "mapping": {"condition": "weather_condition"},
  "fault": {
    "strategy": "retry",
    "max_retries": 3,
    "retry_intervals_ms": [1000, 3000, 10000],
    "on_exhausted": "fallback",
    "fallback_value": {"condition": "unknown", "temperature": 20}
  }
}
```

```
字段说明:

  strategy            retry | fallback | skip | timeout | abort
  max_retries         retry 专用, 默认 3
  retry_intervals_ms  retry 专用, 递增间隔, 默认 [1000, 3000, 10000]
  on_exhausted        retry 全部失败后的降级策略, 默认 abort
  fallback_value      fallback 专用, 默认值
  timeout_seconds     timeout 专用, 默认 5
```

### 嵌套容错

`retry` 可以嵌套降级:

```
retry 3 次 → 全失败 → on_exhausted = "fallback" → 用缓存
retry 3 次 → 全失败 → on_exhausted = "skip"    → 跳过
retry 3 次 → 全失败 → on_exhausted = "abort"   → 停止 (默认)
```

## 四、咖啡厅工作流完整配置

```json
{
  "workflow_id": "coffee_shop_music",
  "name": "咖啡厅音乐推荐",
  "channels": [
    {
      "id": "c_loc",
      "source": "system.location", "target": "system.context-fusion",
      "fault": {"strategy": "fallback", "fallback_value": {"place": "上次咖啡厅"}}
    },
    {
      "id": "c_wth",
      "source": "system.weather", "target": "system.context-fusion",
      "fault": {"strategy": "retry", "max_retries": 2, "on_exhausted": "fallback",
                "fallback_value": {"condition": "unknown", "temp": 20}}
    },
    {
      "id": "c_cam",
      "source": "system.camera", "target": "system.context-fusion",
      "fault": {"strategy": "timeout", "timeout_seconds": 2, "on_timeout": "skip"}
    },
    {
      "id": "c_dev",
      "source": "system.device", "target": "system.context-fusion",
      "fault": {"strategy": "skip"}
    },
    {
      "id": "c_clk",
      "source": "system.clock", "target": "system.context-fusion",
      "fault": {"strategy": "fallback",
                "fallback_value": {"hour": 12, "day": "Saturday"}}
    },
    {
      "id": "c_mus",
      "source": "system.rule-engine", "target": "system.music-player",
      "fault": {"strategy": "skip"}
    }
  ]
}
```

## 五、执行引擎伪代码

```python
SKIP = object()

def execute_workflow(dag):
    results = {}
    
    for node in topological_sort(dag):
        # 收集输入
        inputs = {}
        missing = []
        for channel in dag.input_channels(node):
            source_result = results.get(channel.source)
            if source_result is None or source_result is SKIP:
                inputs[channel.id] = resolve_fault(channel, source_result)
                if inputs[channel.id] is SKIP:
                    missing.append(channel.id)
                    continue
            else:
                inputs[channel.id] = source_result

        # 如果有 abort → 立即终止
        if any_abort(inputs):
            return {"status": "ABORTED", "at": node.id}

        # 执行节点
        try:
            output = execute_node(node, inputs, missing)
            results[node.id] = output
        except Exception as e:
            # 节点执行失败 → 输出通道各自容错
            results[node.id] = e

    return {"status": "COMPLETED", "results": results}


def resolve_fault(channel, error):
    strategy = channel.fault.strategy

    if strategy == "retry":
        for i, interval in enumerate(channel.fault.intervals):
            try:
                sleep(interval)
                return execute_node(channel.source)
            except:
                continue
        return resolve_fault_fallback(channel)  # retry exhausted

    if strategy == "fallback":
        return channel.fault.fallback_value

    if strategy == "skip":
        return SKIP

    if strategy == "timeout":
        result = run_with_timeout(channel.source, channel.fault.timeout_seconds)
        if result is TIMEOUT:
            return resolve_fault_fallback(channel)
        return result

    if strategy == "abort":
        raise WorkflowAborted(channel)
```

## 六、图谱上的表现

```
工作流运行时, 每个节点有一圈状态环:

  ○ 灰色环   = pending (等待执行)
  ◉ amber 脉动 = running (正在执行)
  ● 绿色     = success
  ◉ amber 虚线 = retrying (重试中, 显示剩余次数)
  ◉ 灰色虚线 = fallback (用了默认值)
  ○ 灰色     = skipped (跳过)
  ● 红色     = failed + aborted (整个工作流停止)

连线:
  绿色实线 = 数据正常流过
  amber 闪烁 = 正在重试
  灰色虚线   = 跳过/降级
  红色 ×    = abort 终止
```

## 七、工作流日志

```
执行一次工作流后, 可查看日志:

  location     ✅ success · 12ms
  weather      ⚠️ retry ×1 → success · 2300ms    ← 第一次失败, 第二次成功
  camera       ⏭️ timeout → skipped              ← 超时跳过
  device       ✅ success · 5ms
  clock        ✅ success · 2ms
  fusion       ⚠️ 1 input missing → success · 15ms
  rule         ✅ matched "rainy_cafe" · 3ms
  music        ⏭️ "Stan" not found → "Lose Yourself" · 80ms

  状态: COMPLETED (3 个环节出现容错)
```

## 八、UI 交互

工作流画布中, 点一根连线 → 底部滑出容错面板:

```
┌──────────────────────────────────────┐
│  连线: weather → fusion              │
│                                      │
│  失败时:                             │
│  ○ 停止整个工作流 (默认)            │
│  ● 重试                             │
│      最多 [3] 次                     │
│      间隔 [1s] [3s] [10s]           │
│      全失败后 [降级用默认值 ▼]      │
│  ○ 使用默认值                       │
│      默认值: {condition: unknown}    │
│  ○ 跳过, 不影响下游                 │
│  ○ 超时 [5] 秒后降级                │
│                                      │
│  [确定]                              │
└──────────────────────────────────────┘
```

## 九、文件变更

```
改:
  CHANNEL_MODEL.md                  ← + fault 字段定义
  workflow_executor.py              ← + 容错执行逻辑
  widgetmcp_src/ui/GraphEdge.kt     ← + 容错状态渲染
  widgetmcp_src/.../WorkflowMode.kt ← + 连线容错选择 UI

增:
  tests/test_workflow_resilience.py
```

## 十、测试场景

```
1. 全部正常 → 工作流完成, 无容错触发
2. GPS 超时, fallback → 用缓存, 完成
3. 天气 API 失败, retry × 2 成功 → 完成
4. 天气 API 失败, retry × 3 全败, on_exhausted=fallback → 用缓存, 完成
5. 摄像头超时, skip → 跳过, fusion 缺 1 输入仍工作
6. 支付失败, abort → 工作流立即停止, 下游不执行
7. retry 全败, on_exhausted=abort → 停止
8. 两个原子同时失败, 各自容错 → 完成
```

## 十一、实施

```
1h    CHANNEL_MODEL 加 fault 字段
2h    执行引擎实现 5 种策略 + 嵌套容错
1h    工作流日志 + 状态记录
1h    Android 连线 UI + 图谱状态渲染
1h    测试 (8 个场景)

5h 总计, 零破坏 (默认 abort = 现有行为)
```

---

> **不是原子会坏。是真实世界不可靠。每根连线声明"这里失败了怎么办", 工作流就有弹性。**
