# 工作流引擎 — 可视化积木编排设计

## 1. 项目定位

一个独立的桌面应用，用搭积木的方式将 Claude Code skill、本地脚本、HTTP API 编排成可执行的工作流。

| 维度 | 决策 |
|------|------|
| 场景 | 跨项目多工具编排，手动触发优先，架构预留定时/事件扩展 |
| 编辑方式 | 可视化画布，拖拽节点 + 连线 |
| 执行引擎 | Claude Code 为默认运行时，节点自带执行方式 |
| 画布形态 | Electron 桌面应用，不绑定 Claude Code 进程 |
| 存储 | 全局用户级 `~/.claude-workflow/`，支持导出/导入 JSON |
| 技术栈 | Electron + React + React Flow |

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                    Electron 桌面应用                              │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐  │
│  │   可视化画布 (React)  │  │        主进程 (Node.js)          │  │
│  │                      │  │                                  │  │
│  │  ┌─ 积木面板（左侧）  │  │  ┌─ Skill 扫描器               │  │
│  │  │  skill / script  │  │  │  读取 ~/.claude/skills/      │  │
│  │  │  api / manual    │  │  │  解析 manifest               │  │
│  │  └──────────────────┘  │  └──────────────────────────────┘  │
│  │  ┌─ 画布（中央）      │  │  ┌─ 工作流执行器               │  │
│  │  │  节点拖拽 + 连线  │  │  │  调 claude CLI 执行 skill   │  │
│  │  │  React Flow       │  │  │  调 child_process 跑脚本    │  │
│  │  └──────────────────┘  │  │  调 fetch 发 API 请求        │  │
│  │  ┌─ 属性面板（右侧）  │  │  └──────────────────────────────┘  │
│  │  │  节点参数配置     │  │  ┌─ 存储管理器                  │  │
│  │  │  输入输出映射     │  │  │  读写 ~/.claude-workflow/    │  │
│  │  └──────────────────┘  │  │  导出/导入 JSON              │  │
│  └──────────────────────┘  └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**三大模块：**

1. **渲染进程（React + React Flow）** — 纯 UI，只管画布渲染、拖拽交互、连线、样式。不碰执行逻辑。
2. **主进程（Electron Main）** — 扫描已安装 skill 和本地脚本生成积木列表；接收画布发来的工作流定义并逐节点执行；持久化读写 `~/.claude-workflow/`。
3. **IPC 桥接** — 渲染 ↔ 主进程通过 Electron IPC 通信。画布点"运行"，IPC 发工作流 JSON 到主进程；主进程每执行完一个节点，IPC 推送状态变化回画布实时更新节点颜色。

## 3. 节点模型（积木抽象）

### 3.1 六类内置节点

| 类型 | 颜色 | 说明 | 示例 |
|------|------|------|------|
| Skill | 紫色 | 已安装的 Claude Code skill | `/code-review`、`/bug-hunter` |
| Script | 青色 | 本地可执行脚本或命令 | `pytest --json`、`./deploy.sh` |
| API | 橙色 | HTTP 请求，调用外部服务 | `POST /webhook`、`GET /status` |
| APK | 玫红 | 本地 APK 应用，通过 ADB 安装/启动/测试 | `adb install app.apk`、启动智能体应用 |
| KB | 金色 | 知识库查询，检索 Markdown 文档并注入上下文 | 查询 API 文档、注入项目规范 |
| Manual | 灰色 | 人工确认节点，暂停等待用户操作 | "确认部署到生产？" |

### 3.2 节点统一结构

```typescript
interface WorkflowNode {
  id: string;
  type: "skill" | "script" | "api" | "apk" | "kb" | "manual";
  label: string;
  position: { x: number; y: number };

  // type === "skill"
  skillName?: string;
  skillArgs?: string;

  // type === "script"
  command?: string;
  cwd?: string;
  timeout?: number;

  // type === "api"
  method?: "GET" | "POST" | "PUT" | "DELETE";
  url?: string;
  headers?: Record<string, string>;
  body?: string;

  // type === "apk"
  apkPath?: string;              // APK 文件路径
  adbAction?: "install" | "launch" | "uninstall" | "test";
  packageName?: string;          // 包名（用于 launch/uninstall）
  adbArgs?: string;              // 额外 ADB 参数

  // type === "kb"
  kbPath?: string;               // 知识库目录路径
  query?: string;                // 检索查询（支持变量引用）
  topK?: number;                 // 返回最相关文档数（默认 5）
  outputMode?: "context" | "files"; // 注入上下文 或 输出匹配文件列表

  // type === "manual"
  prompt?: string;
}
```

### 3.3 数据流转

节点之间通过文件路径传递数据：

- 脚本 stdout、API 响应体、skill 输出均存为文件
- 下游节点通过变量表达式引用上游输出

变量表达式：
```
${{ steps.<node-id>.output }}      // 上游节点的输出文件路径
${{ steps.<node-id>.exitCode }}    // 上游节点的退出码
${{ env.HOME }}                    // 环境变量
```

## 4. 画布交互

### 4.1 布局

```
┌────────────┬──────────────────────────────┬───────────┐
│  积木面板   │                              │  属性面板   │
│  (左侧)    │       画布 (中央)              │  (右侧)    │
│            │                              │           │
│  🔍 搜索   │   ┌─────┐    ┌─────┐        │  节点名称   │
│            │   │Lint │───▶│Test │        │  参数配置   │
│  ├ Skill ──│   └─────┘    └──┬──┘        │  超时时间   │
│  │ review  │                 │           │  重试次数   │
│  │ hunter  │            ┌────▼────┐      │           │
│  │ ...     │            │ Deploy  │      │           │
│  ├ Script  │            └─────────┘      │           │
│  ├ API ───│                              │           │
│  └ Manual  │                              │           │
└────────────┴──────────────────────────────┴───────────┘
```

### 4.2 交互清单

- **添加节点**：从左侧面板拖积木到画布，或双击积木自动添加到画布空白处
- **连线**：鼠标悬浮节点露出输出端圆点，拖拽到目标节点输入端口。类型不兼容则连线拒绝
- **配置节点**：点击画布上的节点，右侧属性面板切换为该节点的配置表单
- **画布操作**：滚轮缩放、拖拽平移、框选多节点、Ctrl+Z 撤销、Delete 删除、Ctrl+C/V 复制粘贴
- **运行反馈**：灰色（等待）→ 蓝色脉冲（执行中）→ 绿色（成功）→ 红色（失败，停止后续）

## 5. 执行引擎

### 5.1 执行流程

```
工作流 JSON → 拓扑排序 → 逐节点执行 → 状态实时推送到画布
```

### 5.2 单节点执行

```
1. 解析变量引用（${{ steps.X.output }} → 实际路径）
2. 创建工作目录（~/.claude-workflow/runs/<run-id>/<node-id>/）
3. 按类型派发：

   type=skill  → claude run <skillName> <args>
                 stdout → output 文件

   type=script → child_process.spawn(command, {cwd})
                 stdout → output 文件
                 stderr → error 文件

   type=api    → fetch(url, {method, headers, body})
                 response.body → output 文件
                 response.status → exitCode

   type=kb     → 读取 kbPath 下所有 .md 文件
                 对 query 做全文检索/相似度匹配
                 返回 topK 篇最相关文档拼接为上下文
                 output → output 文件

   type=apk    → adb <action> <apkPath|packageName>
                 install: adb install <apkPath>
                 launch:  adb shell am start -n <packageName>
                 test:    adb shell am instrument <packageName>
                 uninstall: adb uninstall <packageName>
                 stdout → output 文件

   type=manual → IPC 发确认框到渲染进程
                 等待用户点"继续"或"终止"

4. 写入执行结果（output、exitCode、耗时、错误信息）
5. IPC 推送节点状态到画布
6. exitCode !== 0 且未配置"失败继续" → 终止后续节点
```

### 5.3 并发执行

并行分支（无相互依赖的节点）同时启动：

```
     ┌─────┐
     │Lint │──┬──▶ Test ──▶ Deploy
     └─────┘  │
              └──▶ Build ──┘
```

### 5.4 运行记录

```
~/.claude-workflow/runs/<run-id>/
├── workflow.json       # 工作流快照
├── status.json         # 整体状态和各节点状态
├── <node-1>/
│   ├── output.txt
│   └── error.txt
├── <node-2>/
│   ├── output.txt
│   └── error.txt
└── ...
```

## 6. 存储与可移植性

### 6.1 目录结构

```
~/.claude-workflow/
├── workflows/                 # 所有工作流定义
│   ├── deploy-full.json
│   └── quick-review.json
├── templates/                 # 导出的可分享模板
│   └── deploy-full.template.json
├── runs/                      # 历史运行记录
├── node-cache/                # skill/脚本 列表缓存
│   └── nodes.json
└── settings.json              # 应用全局设置
```

### 6.2 工作流文件格式

```json
{
  "version": "1.0",
  "name": "发布流程",
  "description": "lint → test → build → deploy",
  "nodes": [
    {
      "id": "n1",
      "type": "skill",
      "label": "代码审查",
      "position": { "x": 100, "y": 200 },
      "skillName": "code-review",
      "skillArgs": "--effort medium"
    },
    {
      "id": "n2",
      "type": "script",
      "label": "运行测试",
      "position": { "x": 400, "y": 200 },
      "command": "pytest --json",
      "cwd": "${{ env.PWD }}",
      "timeout": 120
    }
  ],
  "edges": [
    { "source": "n1", "target": "n2" }
  ]
}
```

### 6.3 导出/导入

- **导出**：菜单 → "导出模板" → 生成 `.template.json`，敏感信息参数化
- **导入**：菜单 → "导入模板" → 选择 `.json` 或 `.template.json`，节点出现在画布
- 未来可扩展模板市场 URL，下载社区模板

## 7. 未来扩展点

- **定时触发**：节点新增 cron 配置，主进程内置调度器
- **事件触发**：监听文件变更、git hook、webhook 等
- **节点插件系统**：允许第三方注册自定义节点类型
- **模板市场**：在线仓库，浏览和下载社区工作流模板
