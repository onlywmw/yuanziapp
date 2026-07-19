# 工作流容错设计

> **问题**: 一个原子出错, 整个工作流不能停
> **方案**: 每个连线声明容错策略 — 不是修原子, 是让工作流有弹性

---

## 一、容错策略

每个连线可声明一种策略:

```
策略         行为                         适用场景
──────────────────────────────────────────────────
retry        重试 N 次, 间隔递增          网络抖动
fallback     用默认值替代                 传感器偶发失败 (用缓存/上次值)
skip         跳过这个节点, 继续下一环节    非关键输入 (摄像头没拍到不影响)
timeout      等 X 秒, 超时就降级           外部 API 慢
abort        出错立即停止整个工作流        关键路径 (支付/安全)
```

## 二、在连线上声明

```
工作流画布中, 每个连线有一个容错标记:

  camera ──→ context-fusion
            │
            [容错: skip]  ← 点连线, 弹出容错选项

  weather ──→ context-fusion
            │
            [容错: fallback, 上次天气]

  music-player ←── rule-engine
            │
            [容错: skip, 下一首]
```

## 三、咖啡厅场景的容错配置

```
location  ──[fallback: 上次位置]──→
camera    ──[skip]────────────────→
weather   ──[fallback: 缓存30min]─→ context-fusion
device    ──[skip]────────────────→
clock     ──[timeout: 2s]─────────→
                                       │
                                       ▼
                                  rule-engine
                                       │
                              ──[skip: 下一首]──→ music-player
```

## 四、工作流执行时的表现

```
执行 location:    GPS 超时 → fallback → 用上次: "星巴克·南京西路"
执行 weather:     API 正常 → "rain, 18°C"
执行 camera:      识别超时 → skip → 不影响 fusion
执行 device:      蓝牙正常 → "AirPods connected"
执行 clock:       正常
       │
       ▼
context-fusion:  输入不完整 (缺 camera), 但够用
       │
       ▼
rule-engine:    匹配到 "rainy_headphones" → 推荐音乐
       │
       ▼
music-player:    找不到《Stan》→ skip → 《Lose Yourself》

结果: 工作流完成。人听到歌了。即使中间三个环节出了问题。
```

## 五、工作流运行视图

```
工作流运行时, 每个节点和连线有颜色:

  绿色闪烁: 正在执行
  绿色实线: 执行成功
  amber+重试图标: 重试中 (余 2 次)
  amber+fallback图标: 降级运行 (用了缓存)
  灰色+skip图标: 跳过 (不影响结果)
  红色: 失败 (且策略是 abort — 整个工作流停了)
```

## 六、规则

```
默认策略:
  每个连线默认是 abort (保持安全 — 不声明容错就不容错)

作者声明:
  画工作流时, 对每个连线点选容错策略
  系统不替作者决定 — 只有作者知道哪个环节可以容错

验证:
  保存工作流时检查:
    环形链路不能全部 abort (至少一个容错出口)
    终端执行原子不建议 skip (音乐播放跳过 → 没结果)
```

## 七、实施

```
改 3 处:

  CHANNEL_MODEL.md       ← 连线模型加 fault_strategy 字段
  WORKFLOW_CONNECTION_RULES.md ← 容错=连线的新维度
  工作流执行引擎          ← 执行时读容错策略

  零破坏: 连线默认 abort, 和现在行为一致
```

---

> **不是原子会坏。是工作流中的环节可能失败。容错声明让工作流知道"这里失败没关系"。**
