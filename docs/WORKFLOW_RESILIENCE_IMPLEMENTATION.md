# 工作流容错实施方案

> **改动范围**: 通道模型 + 执行引擎 + 连线 UI
> **破坏性**: 零 — 默认 abort, 和现在行为一致

---

## 一、通道模型扩展

`CHANNEL_MODEL.md` 中连线定义加一个字段:

```json
{
  "channel_id": "c1",
  "type": "map",
  "source": "weather",
  "target": "context-fusion",
  "mapping": {"condition": "weather_condition"},
  "fault": {
    "strategy": "fallback",
    "fallback_value": {"condition": "unknown", "temperature": 20},
    "max_retries": null,
    "timeout_seconds": null
  }
}
```

`fault` 字段定义:

| 字段 | 说明 |
|------|------|
| strategy | retry / fallback / skip / timeout / abort |
| fallback_value | fallback 时使用的默认值 |
| max_retries | retry 最多重试次数 (默认 3) |
| retry_interval_ms | 重试间隔 (默认 1000, 3000, 10000) |
| timeout_seconds | timeout 超时秒数 |

## 二、执行引擎改动

文件: `mcp-yuanzi-bridge/workflow_executor.py` (或现有执行逻辑)

```
现有执行流程:
  for node in topological_order:
    output = execute(node)
    pass_to_next(node, output)

改动后:
  for node in topological_order:
    for each input_channel:
      if channel.fault == "skip" and input is None:
        continue     ← 跳过, 该节点得不到这个输入
      if channel.fault == "fallback" and input is None:
        input = channel.fallback_value
      if channel.fault == "timeout":
        input = execute_with_timeout(node, channel.timeout_seconds)
    
    result = execute(node)
    
    if result is error:
      for each output_channel:
        if channel.fault == "retry":
          result = retry(node, channel.max_retries, channel.retry_intervals)
        if channel.fault == "skip":
          continue     ← 不传给下游
        if channel.fault == "abort":
          raise WorkflowAborted

    pass_to_next(node, result)
```

核心逻辑:

```python
FAULT_STRATEGIES = {
    "retry": lambda node, ch: retry_with_backoff(node, ch.max_retries, ch.intervals),
    "fallback": lambda node, ch: ch.fallback_value,
    "skip": lambda node, ch: SKIP_SIGNAL,
    "timeout": lambda node, ch: run_with_timeout(node, ch.timeout_seconds),
    "abort": lambda node, ch: raise AbortError,
}

def resolve_fault(node, channel, error):
    strategy = channel.get("fault", {}).get("strategy", "abort")
    handler = FAULT_STRATEGIES[strategy]
    return handler(node, channel)
```

## 三、连线 UI

在 Android 工作流画布中, 点一条连线 → 弹出容错选择:

```
┌──────────────────────────────┐
│  连线: weather → fusion      │
│                              │
│  容错策略:                    │
│  ○ 遇错即停 (默认)           │
│  ● 重试 3 次                 │
│  ○ 使用默认值替代            │
│  ○ 跳过, 不影响流程          │
│  ○ 超时 5 秒后降级           │
│                              │
│  [确定]                      │
└──────────────────────────────┘
```

## 四、运行时状态

工作流执行时, 每个节点记录容错事件:

```
执行日志:
  node: weather
    status: success

  node: camera
    status: skipped
    reason: "timeout after 2s"
    fault_strategy: skip

  node: context-fusion
    status: success
    note: "1 input missing, 4 inputs ok"

  node: music-player
    status: success
    fault_event: "track 'Stan' not found → skipped → 'Lose Yourself'"
```

## 五、测试

```
test_fallback_on_sensor_failure:
  → GPS 超时 → fallback 用缓存 → 工作流完成

test_skip_non_critical:
  → camera 失败 → skip → 不影响其余环节

test_retry_recovers:
  → 第 1 次失败 → 重试 → 第 2 次成功

test_abort_on_critical:
  → 支付环节失败 → abort → 工作流立即停止

test_partial_input_fusion:
  → 5 个输入, 2 个失败 (fallback) → fusion 正常工作
```

## 六、文件变更

```
改:
  CHANNEL_MODEL.md               ← 连线加 fault 字段
  workflow_executor.py            ← 执行时读容错策略
  widgetmcp_src/.../WorkflowMode.kt ← 连线 UI 加容错选择

增:
  tests/test_workflow_resilience.py
```

## 七、实施

```
1h: 通道模型加 fault 字段
2h: 执行引擎实现 5 种策略
1h: Android 连线 UI 容错选择
1h: 测试
```

---

> **每根连线声明"这里失败了怎么办"。默认 abort, 和现在一模一样。**
