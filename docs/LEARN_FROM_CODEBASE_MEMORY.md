# 从 codebase-memory-mcp 可借鉴的

> **定位**: 不照抄, 只取对 Yuanzi 有用的

---

## 1. 安装体验 — 一行命令搞定

```
他:
  curl ... | bash
  单二进制, 零依赖, 30 秒装完

我们:
  Python + Termux + Chaquopy + APK 构建
  新手装不上去

可借鉴:
  · CLI 工具 (yuanzi-cli) 打包为单二进制 (PyInstaller / Nuitka)
  · 提供一键安装脚本
  · Chaquopy 内嵌后, APK 就是单文件安装
```

## 2. Web 图谱 UI — 浏览器就能看

```
他:
  localhost:9749 → 3D WebGL 图谱
  不需要装 App, 浏览器打开就能看

我们:
  Android APK 原生 Canvas
  移动端体验好, 但没有桌面/浏览器入口

可借鉴:
  · 加一个轻量 Web UI (FastAPI + HTML + Canvas/Three.js)
  · 开发调试时用浏览器看图谱更方便
  · 不是替代 Android UI, 是补充 — 桌面端也能看
  · 已有 FastAPI + /docs → 加 /graph 页面即可
```

## 3. 自动检测环境

```
他:
  install 自动检测已安装的 AI agent → 自动配置 MCP 条目

我们:
  安装工作流时 → 自动检测设备 → 匹配连接器

  这个我们已经在做了 (connector auto-match)
  方向一致, 不需额外借鉴
```

## 4. 索引速度 — 对搜索有启发

```
他:
  SQLite + 内存 + LZ4 压缩 → Linux 内核 3 分钟索引完

我们:
  语义搜索 (M5) 的索引重建可以借鉴:
    · 全部在内存中处理, 最后一次性写 SQLite
    · 目前 61 个原子重建足够快, 但未来 10000+ 需要优化
```

## 5. Cypher 查询 — 对搜索的启发

```
他:
  支持 Cypher 图数据库查询语法 (Neo4j 风格)
  MATCH (f:Function)-[:CALLS]->(c:Function) WHERE ...

我们:
  当前搜索: JSON API + embedding
  未来可以加图查询:
    "找出所有依赖 file-read 且评分 ≥ 4 的原子"
    → 用 Cypher 一句话, 不用写代码
```

---

## 不借鉴的

```
· 3D → 我们用 Obsidian 2D 暗色美学, 更符合极客审美
· 单文件 C 二进制 → 我们有 Python 生态, 够用
· Tree-sitter AST → 我们不分析代码
· 158 种语言 → 我们是能力平台, 不是代码分析器
```

---

## 优先级

```
P0:
  一键安装脚本 (curl | bash)  ← 学习他的安装体验

P1:
  浏览器图谱 UI (FastAPI + /graph)  ← 补充桌面端入口

P2:
  Cypher 图查询  ← 搜索增强
  索引速度优化  ← 大规模场景
```

---

> **他的强项: 安装快、浏览器看、单文件。取这三个, 其他的我们有自己的路。**
