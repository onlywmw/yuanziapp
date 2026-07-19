# 工作流执行引擎

> **定位**: 引擎层 — 怎么跑。Graph Engine 管渲染, Workflow Engine 管执行。
> **来源**: 从 DESIGN_CHANNEL_SPEC 和 resilience 中提取执行逻辑, 在此独立成文

---

## 一、架构位置

```
引擎层:

  Graph Engine (怎么画)           Workflow Engine (怎么跑)
  ─────────────────────           ──────────────────────
  Renderer / ForceLayout          拓扑排序 → 逐节点执行
  Camera / Interaction            通道转换 (5种)
  Animation / Virtualization      容错处理 (5种策略)
  NodeMgr / EdgeMgr              运行日志 / 状态追踪
  Store / 通道渲染                并发控制 / 资源锁
```

## 二、执行流程

```
1. 加载工作流 DAG
      ↓
2. 拓扑排序 (依赖在前, 目标在最后)
      ↓
3. 逐节点执行:
   a. 收集所有输入通道的数据
   b. 应用通道转换 (direct/map/transform/merge/split)
   c. 执行原子 handler
   d. 容错处理 (retry/fallback/skip/timeout/abort)
   e. 记录结果 + 状态
      ↓
4. 全部完成 → 返回最终结果
```

## 三、核心数据结构

```
WorkflowRun:
  run_id: string
  workflow_id: string
  status: pending | running | completed | failed | aborted
  node_states: Map<nodeId, NodeState>
  started_at / completed_at

NodeState:
  node_id: string
  status: pending | running | completed | failed | skipped
  input: dict           ← 经过通道转换后的输入
  output: dict          ← handler 返回的结果
  error: string | null
  retry_count: int
  started_at / completed_at
  duration_ms: int
```

## 四、并发与资源锁

```
并发执行:
  拓扑排序后, 同一层级的节点可并行执行
  没有依赖关系的节点之间不互相等待

资源锁:
  节点声明 resource.exclusive = ["filesystem"]
  调度器检查:
    同一层有 file-write 和 file-read 都要用 filesystem
    → 串行执行 (先 write 后 read)
    → 不冲突的节点仍并行
```

## 五、运行日志

```
每个工作流运行产生结构日志:

{
  "run_id": "run_abc",
  "workflow": "coffee_shop_music",
  "status": "completed",
  "duration_ms": 2340,
  "node_runs": [
    {"node": "location",  "status": "completed", "duration_ms": 230},
    {"node": "weather",   "status": "retry→success", "duration_ms": 3200, "retries": 1},
    {"node": "camera",    "status": "skipped", "reason": "timeout"},
    {"node": "fusion",    "status": "completed", "duration_ms": 45},
    {"node": "music",     "status": "completed", "duration_ms": 80}
  ],
  "faults": [
    {"node": "weather", "strategy": "retry", "attempts": 2, "recovered": true},
    {"node": "camera",  "strategy": "skip", "reason": "timeout after 2s"}
  ]
}
```

## 六、API

```
POST /api/v1/workflows/{id}/run
  → 返回 run_id, 启动异步执行

GET /api/v1/runs/{run_id}
  → 返回 WorkflowRun 状态 + 日志

GET /api/v1/runs/{run_id}/stream
  → SSE 流式推送每个节点的状态变化
  → UI 实时更新图谱中的节点颜色和通道动画
```

## 七、与 Graph Engine 的协作

```
执行引擎更新节点状态 → Graph Store 同步 → Renderer 重绘

  执行中: NodeState = running
    → GraphView: 节点 amber 脉动 + 连线数据流动画

  执行完成: NodeState = completed
    → GraphView: 节点绿色 + 连线绿色

  容错跳过: NodeState = skipped
    → GraphView: 节点灰色 + 连线灰色虚线

  执行失败: NodeState = failed
    → GraphView: 节点红色 + 连线红色 ×

两个引擎通过 GraphStore 通信。一个写状态, 一个读状态。
```

## 八、实施

```
P0 (已有):
  · 拓扑排序 (registry.resolve_dependencies)
  · 通道转换 (DESIGN_CHANNEL_SPEC 五种类型)
  · 容错策略 (retry/fallback/skip/timeout/abort)

P1 (需新增):
  · 并发执行引擎 (同层并行 + 资源锁)
  · SSE 流式状态推送
  · 运行日志存储
```
