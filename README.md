# Yuanzi App

> **让每一个 AI 能力都成为一个可被发现、可被组合、可被验证的"原子"。**

## 这是什么

Yuanzi 是一个**原子化 AI 工具生态系统**。把能力拆成独立"原子"——从文件读写到天气感知、从数据库查询到意图理解——通过注册中心统一管理，
在 Android 设备上以知识图谱形式呈现。

人可以自然语言搜索匹配的原子能力，拖动滑动条在"管道视角"和"作品视角"之间切换，
创建自己的工作流，发布自己的作品，并通过区块链公证所有权。

## 架构

```
三层:

  基础层    原子 (五类25个) · 通道 (5种) · 工作流 · 注册中心 · API
  发现层    市场 · 搜索 · 安装 · 评分 · 信任
  引擎层    知识图谱渲染 · 力导向布局 · 混音台 · 参数面板 · 模板
```

## 核心特性

```
· 五类原子     工具/感知/融合/决策/执行 — 从数据处理到理解世界
· 通道系统     直通/映射/转换/合并/分流 — 可复用、可测试、有版本
· 知识图谱     Obsidian 风格, 暗色背景, 节点发光, 力导向布局
· 工作流引擎   拓扑排序, 连线容错, 感知→融合→决策→执行全自动
· 视角混合器   一根滑动条: 管道视角 ↔ 作品视角
· AI 意图理解  本地 ONNX 模型, 理解自然语言 → 匹配工作流
· 区块链公证   自己的链, 不可篡改的所有权证明
· 作者第一     每个原子必须有作者
```

## 技术栈

```
后端        Python 3.10+ / FastAPI / SQLite
前端        Android (Kotlin) + Chaquopy (Python 内嵌 APK)
测试        263 全部通过 · black + ruff 门禁 · CI 绿灯
链          Yuanzi Chain (本地, Merkle 验证, 未来分布式)
```

## 项目状态

| 里程碑 | 进度 |
|--------|------|
| M1-M5 | ✅ 已完成 |
| M6 安全 | ✅ 已完成 |
| M7 原子市场与工作流 | 📐 设计就绪 |
| M8 人机体验层 | 📐 设计就绪 |

## 架构文档

47 份设计文档 → [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md)

```
一、基础层      原子体系 · 通道体系 · 注册中心 · AI/区块链
二、发现层      市场 · 评分 · 安装 · 联邦注册
三、引擎层      图谱SDK · 混音台 · 参数面板 · 模板系统
四、终端        APK规格 · Python内嵌
五、质量治理     测试规范 · 隔离加固 · 验证方案
```

## 快速开始

```bash
# 测试
python -m pytest mcp-yuanzi-bridge/tests/ base-atoms/tests/ yuanzi-cli/tests/ -q

# 链
python yuanzi_chain/chain.py status   # 查看链状态
python yuanzi_chain/chain.py verify   # 验证链完整性

# 验证全量
bash scripts/verify-all.sh

# 构建 APK → docs/APK_BUILD_GUIDE.md
```

## 许可证

MIT
