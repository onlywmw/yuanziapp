# 原子分类体系

> **定位**: 所有原子的完整分类 — 从 v1 两层的 ADR 到 v2 五类 + 连接器 + 人原子
> **合并**: ADR_ATOM_MODEL(v1) + DESIGN_ATOM_V2_CLASSIFICATION(v2)

---

## 一、两层模型

```
基础原子 (system.*):
  系统内置, 不可注册, 不可删除, 随系统升级
  通用逻辑, 无平台差异

注册原子:
  可注册, 可发现, 可安装, 可删除, 有作者
```

## 二、六类原子

```
工具 (function)    数据处理          math-calc, string-split, json-parse
感知 (sensor)      世界输入          location, camera, weather, device
融合 (fusion)      多源→情境         context-fusion
决策 (rule)        情境→动作         rule-engine
执行 (actuator)    世界输出          music-player, notification, vibrate
连接 (connector)   平台通路          location-android, music-spotify
```

## 三、特殊原子

```
人原子 (person):
  最丰富的场。两层: shown(展示的) + actual(实际的)
  档案: 节奏/回应/沉默/连接/成长
  和其他原子一样参与共振

AI 原子 (intelligence):
  system.ai — 本地 ONNX, 意图理解
```

## 四、上下文注解

```
感知原子     = 上下文提供者, 不被直接引用
执行原子     = 最终输出, 用户能感知
工具原子     = 中间处理, 不是源头也不是终点
连接原子     = 借用平台能力, 接口统一

工作流自动识别:
  感知原子并行 → 融合收集 → 决策选择 → 执行输出
```
