# HubStation MVP 设计规格

**日期：** 2026-06-06
**状态：** 待实现
**范围：** MVP — 文字需求 → 中转站 → DeepSeek Web 提问

---

## 一、目标

构建中转站核心骨架，验证"输入适配器 → 转换器 → 输出适配器"核心链路。
第一个具体场景：用户通过 CLI 输入文字需求，中转站处理后，自动打开 DeepSeek 网页填入 Prompt 并提交。

---

## 二、架构

三个核心抽象 + 一个编排引擎：

```
InputAdapter  →  Transformer  →  OutputAdapter
   (接收)          (转换)           (投递)
     │                │                │
 RawMessage    StructuredMessage   DeliveryResult
```

### 2.1 数据结构

**RawMessage** — 输入层统一封装
- `source: "cli" | "file" | "webhook"` — 来源标识
- `content: str` — 原始文本内容
- `metadata: dict` — 时间戳、标签等元信息

**StructuredMessage** — 转换后的结构化消息
- `type: str` — 消息类型 (prompt / ticket / report / ...)
- `target: str` — 目标下游标识 (deepseek / chatgpt / notion / ...)
- `payload: str` — 已格式化的最终文本
- `origin: RawMessage` — 引用原始输入，保持溯源链

**DeliveryResult** — 投递结果
- `success: bool`
- `target: str`
- `error: str | None`

### 2.2 核心接口 (ABC)

**InputAdapter**
- `receive() -> RawMessage`
- MVP 实现：`CliInputAdapter` — 命令行交互式输入

**Transformer**
- `transform(RawMessage) -> StructuredMessage`
- MVP 实现：`PromptTemplateTransformer` — Jinja2 模板包裹

**OutputAdapter**
- `send(StructuredMessage) -> DeliveryResult`
- MVP 实现：`DeepSeekWebAdapter` — Playwright 操控浏览器

### 2.3 Engine

`Engine` 类负责串联三组件，从 `config.yaml` 读取注册表，按 pipeline 配置执行。

---

## 三、项目结构

```
hubstation/
├── core/
│   ├── messages.py        # RawMessage, StructuredMessage, DeliveryResult
│   ├── interfaces.py      # InputAdapter, Transformer, OutputAdapter (ABC)
│   └── engine.py          # 编排器
├── adapters/
│   ├── input/
│   │   └── cli_input.py   # CLI 交互式输入
│   └── output/
│       └── deepseek_web.py # Playwright → DeepSeek
├── transformers/
│   └── prompt_template.py # 模板化 Prompt
├── main.py                # CLI 入口
└── config.yaml            # 适配器注册 + 转换规则配置
```

---

## 四、执行流程

1. 用户运行 `python main.py send --to deepseek`
2. `CliInputAdapter.receive()` — 交互式获取用户输入文本
3. `PromptTemplateTransformer.transform()` — 将文本包裹为测试工程师 Prompt
4. `DeepSeekWebAdapter.send()` — Playwright 启动 Chromium，打开 chat.deepseek.com，填入 Prompt，点击发送
5. 输出 `DeliveryResult` 到终端

---

## 五、错误处理

| 场景 | 处理 |
|------|------|
| DeepSeek 页面选择器失效 | 选择器提取到 config.yaml，不硬编码在代码中 |
| 网络超时 | 重试 3 次，指数退避（1s / 2s / 4s），最终失败返回 error |
| 需要登录 | 检测页面是否有登录墙，若有则暂停等待用户手动登录 |
| Playwright 未安装 | 启动时检查 `playwright install` 状态，给出明确错误提示 |

---

## 六、技术选型

- **语言：** Python 3.11+
- **浏览器自动化：** Playwright (`playwright` pip 包)
- **模板：** Jinja2（后续扩展模板时可复用）
- **配置：** PyYAML
- **包管理：** pip / uv

---

## 七、不在本 MVP 范围

- 可视化画布 / Web UI
- 事件总线 / 多节点路由
- 文档图存储
- 反馈回路
- 多个 Input/Output Adapter（架构支持但暂不实现）
- LLM 驱动的 Transformer（先用简单模板）

---

## 八、验收标准

1. `python main.py send --to deepseek` 可以运行
2. 输入文字后，浏览器自动打开 DeepSeek 并填入 Prompt
3. 终端正确显示 DeliveryResult 成功/失败状态
4. 网络异常时有明确错误提示，不静默失败
