# LLM 排行榜实时追踪悬浮窗 — 设计文档

## 概述

一个 Windows 桌面悬浮窗，展示国内外主流大模型评测榜单的实时排名。
国内/国外模型一键筛选，多榜单多领域切换，排名历史变化追踪，定时自动刷新。

- **目标用户**: 个人使用
- **平台**: Windows 11, Python 3.12+, tkinter
- **形态**: 始终置顶悬浮窗，无边框，半透明

---

## 数据架构

### 数据库 (SQLite: `data/rankings.db`)

```
benchmarks          — 榜单
  id, name, category(cn/global), url, description

domains             — 能力领域
  id, benchmark_id(FK), name, sort_order

models              — 模型字典
  id, name, organization, country(cn/global), is_open_source

rankings            — 当前快照
  id, domain_id(FK), model_id(FK), rank, score, recorded_at

ranking_history     — 历史记录
  id, domain_id(FK), model_id(FK), rank, score, rank_change, score_change, recorded_at
```

关系: Benchmark 1→N Domain 1→N Ranking → Model

筛选逻辑: `models.country` 字段，支持 cn/global/all 三态切换。

### 数据源

| 分类 | 榜单 | 领域（部分） |
|------|------|-------------|
| 国内 | SuperCLUE | 综合, 文科, 理科, 代码, 数学, Agent, 幻觉控制, 指令遵循 |
| 国内 | OpenCompass | 综合, AIME, IFEval, MMLU-Pro, LiveCodeBench, GPQA-Diamond, HLE |
| 国际 | LMSYS Chatbot Arena | Overall, Coding, Math, Creative Writing, Long Query, Multi-Turn |
| 国际 | MMLU-Pro | Overall, STEM, Humanities, Social Sciences |
| 国际 | HumanEval+ | Overall (代码生成评分) |

扩展更多榜单时，追加到 benchmarks 表 + 对应 domains 即可。

---

## UI 设计

### 窗口布局

```
┌──────────────────────────────────────┐
│ 📊 LLM 排行榜       🇨🇳 🌍 🌐  ↻ ⤓ ✕│  标题栏 + 区域筛选
├──────────────────────────────────────┤
│ [SuperCLUE] [OpenCompass] [LMSYS]    │  一级 Tab: 榜单切换
│  [MMLU] [HumanEval]                  │  (滚轮可翻页)
├──────────────────────────────────────┤
│ 综合 │ 代码 │ 数学 │ Agent │ 文科 │  │  二级 Tab: 领域切换
├──────────────────────────────────────┤
│                                      │
│ #  模型                 机构   得分  │
│ 🥇 Claude Opus 4.5  Anthropic 68.3 │
│     ↑2 +3.5                         │  排名变化 + 得分变化
│ 🥈 Qwen3-Max 🇨🇳      阿里   60.6  │
│     ↓1 -0.8                         │
│ 🥉 GPT-5.2           OpenAI  64.3  │
│     →0 +0.2                         │
│                                      │
├──────────────────────────────────────┤
│ ✅ 更新于 12:30    下次刷新: 05:58  │  状态栏
└──────────────────────────────────────┘
```

### 交互

| 操作 | 效果 |
|------|------|
| 标题栏拖动 | 移动窗口 |
| 🇨🇳/🌍/🌐 按钮 | 筛选国内/国外/全部模型 |
| 一级 Tab 点击 | 切换榜单，二级 Tab 自动切换 |
| 二级 Tab 点击 | 切换领域，排名列表刷新 |
| 滚轮在窗口 | 切换一级 Tab |
| 鼠标悬停行 | tooltip 显示最近 3 次历史变化 |
| 双击标题栏 | 切换置顶/取消置顶 |
| ↻ 按钮 | 手动刷新 |
| ⤓ 按钮 | 最小化到托盘 |
| ESC | 最小化 |

### 变化指示

- `↑N` 绿色: 排名上升 N 位
- `↓N` 红色: 排名下降 N 位
- `→0` 灰色: 排名不变
- `+X` 绿色: 得分增加
- `-X` 红色: 得分降低

---

## 抓取策略

### 双层数据获取

| 层 | 方式 | 职责 |
|----|------|------|
| 离线兜底 | `seed_data.py` 硬编码 | 断网/首次启动时立即显示已知数据 |
| 在线更新 | `fetcher.py` 后台 HTTP 抓取 | 定时尝试从官网拉最新排名 |

### 抓取流程

```
启动 → 加载本地 SQLite → 显示窗口
     → 后台线程: 逐个榜单 HTTP 抓取
              → 与旧排名对比 → 计算 rank_change / score_change
              → 写入 rankings + ranking_history
              → 通知 UI 刷新
     → 调度下次抓取 (默认 6h, 可配置)
```

### 容错

- 单个榜单抓取失败 → 该榜单标灰，保留上次数据
- 全部失败 → 沿用上次数据，状态栏显示上次成功时间
- 连续 3 次失败 → 延长间隔到 12h

---

## 代码架构

```
llm_rank_float.py          # 主入口 (双击启动)
├── config.py               # 配置: 抓取间隔, URL, 颜色/字体
├── db.py                   # SQLite: 建表, CRUD, 历史对比
├── models.py               # 数据结构 (dataclass)
├── fetcher.py              # 后台抓取线程: 调度, HTTP, 对比, 入库
├── seed_data.py            # 内置排名快照 (离线兜底)
├── ui/
│   ├── __init__.py
│   ├── app.py              # FloatingRankWindow 主窗口
│   ├── title_bar.py        # 标题栏 + 筛选按钮
│   ├── tab_bar.py          # 一级/二级 Tab
│   ├── rank_list.py        # 排名列表 + 变化箭头 + tooltip
│   └── status_bar.py       # 底部状态栏
└── data/
    └── rankings.db         # SQLite (自动创建)
```

### 启动流程

1. `db.py` 检查/创建表结构
2. 查询 rankings → 空则从 `seed_data.py` 灌入
3. `ui/app.py` 加载排名到 UI → 显示悬浮窗
4. `fetcher.py` 后台线程启动 → 抓取 → 写库 → 通知 UI 刷新

### 依赖

- Python 标准库: tkinter, sqlite3, threading, urllib, json, dataclasses
- 零外部 pip 依赖
