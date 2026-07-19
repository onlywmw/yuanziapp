# Yuanzi App

> **让每一个 AI 能力都成为一个可被发现、可被组合、可被验证的"原子"。**

## 这是什么

Yuanzi 是一个**原子化 AI 工具生态系统**。把能力拆成独立"原子"——从文件读写到天气感知、从数据库查询到意图理解——通过注册中心统一管理，
在 Android 设备上以知识图谱形式呈现。

人可以自然语言搜索匹配的原子能力，拖动滑动条在"管道视角"和"作品视角"之间切换，
创建自己的工作流，发布自己的作品，并通过区块链公证所有权。

## 原子体系

```
五类原子 (25 个):
  工具 (13)     file-read, http-get, math-calc, encrypt-aes...
  感知 (6)      location, camera, weather, device, clock
  融合 (1)      context-fusion
  决策 (1)      rule-engine
  执行 (4)      music-player, notification, display, vibrate

通道 (5 种):
  直通线 / 映射线 / 转换线 / 合并线 / 分流线

注册原子 (61+):
  mcp.postgres, mcp.mysql, mcp.s3... 终端原子 (商品/服务/作品)
```

## 核心特性

```
· 知识图谱     Obsidian 风格, 暗色背景, 力导向布局, 节点发光
· 视角混合器   一根滑动条: 管道视角 ↔ 作品视角
· 参数面板     8 个推子 + 4 种配色一键切换
· 原子灵魂     风格/受众/基调/品质/叙事 — 让原子切中人心
· 工作流引擎   拓扑排序, 连线容错, 感知→融合→决策→执行全自动
· AI 意图理解  本地 ONNX 模型, 理解自然语言 → 匹配工作流
· 区块链公证   自己的链, 不可篡改的所有权证明
· 作者第一     每个原子必须有作者, 人通过创造的工具连接彼此
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

35 份设计文档 → [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md)

```
原子体系 → 灵魂与可见性 → 连线与通道 → 图谱引擎
→ 阶段设计 → 终端 & APK → AI & 区块链 & 体验 → 质量治理
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
