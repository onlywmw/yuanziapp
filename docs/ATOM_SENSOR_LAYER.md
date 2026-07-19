# 感知原子层

> **发现**: 当前 13 个基础原子全是"工具原子"——处理数据。缺了"感知原子"——捕捉真实世界。
> **场景**: 位置 + 摄像头 + 天气 + 设备 → 触发终端 → 播放下雨天的歌

---

## 一、原子分类补全

```
当前分类 (按 ARCHITECTURE.type):

  function      ← 纯计算 (math-calc, string-split)
  external      ← 外部调用 (http-get, http-post)
  rule          ← 规则判断
  agent         ← AI 代理
  mcp-server    ← MCP 服务
  data          ← 数据源
  schema        ← Schema 定义
  gateway       ← 网关

缺失:
  sensor        ← 感知真实世界 (GPS/摄像头/麦克风/蓝牙/传感器)
  actuator      ← 作用于真实世界 (播放/显示/通知/震动)
```

---

## 二、感知原子

### 2.1 位置感知

```
atom_id: system.location
输入:    (无 — 主动采集)
输出:    {
           latitude, longitude,
           place: "星巴克 · 南京西路店",
           type: "cafe",
           accuracy: 5m,
           timestamp
         }
触发:    进入/离开地理围栏
```

### 2.2 视觉感知

```
atom_id: system.camera
输入:    (无 — 主动采集)
输出:    {
           objects: [{label: "coffee cup", confidence: 0.92}],
           scene: "indoor · cafe",
           text: "拿铁 ¥32",
           timestamp
         }
触发:    检测到特定物体/场景
```

### 2.3 天气感知

```
atom_id: system.weather
输入:    {location: "上海"}
输出:    {
           condition: "rain",
           temperature: 18,
           humidity: 85,
           forecast: "持续小雨"
         }
触发:    天气变化
```

### 2.4 设备感知

```
atom_id: system.device
输入:    (无 — 主动采集)
输出:    {
           bluetooth: [{device: "AirPods Pro", connected: true}],
           wifi: "Starbucks WiFi",
           battery: 72,
           screen_on: true
         }
触发:    设备连接/断开
```

### 2.5 时间感知

```
atom_id: system.clock
输入:    (无)
输出:    {
           hour: 15,
           day: "Saturday",
           is_weekend: true,
           season: "summer"
         }
触发:    特定时间/日期
```

### 2.6 生物感知 (未来)

```
atom_id: system.biometric (未来)
输入:    (手环/手表)
输出:    {heart_rate, stress_level, activity}
触发:    心率/压力变化
```

---

## 三、上下文融合原子

```
atom_id: system.context-fusion

不是感知 — 是把多个感知融合成一个"情境":

  输入:
    location  → {type: "cafe", place: "星巴克"}
    weather   → {condition: "rain"}
    device    → {bluetooth: [{name: "AirPods", connected: true}]}
    clock     → {hour: 15, day: "Saturday"}

  输出:
    {
      situation: "rainy_saturday_cafe",
      mood: "melancholy",
      tags: ["rain", "coffee", "alone", "headphones", "weekend"],
      confidence: 0.85
    }
```

## 四、规则/决策原子

```
atom_id: system.rule-engine

输入情境 → 匹配规则 → 输出决策:

  规则示例:
    IF situation = "rainy_saturday_cafe"
       AND device.bluetooth CONTAINS "headphones"
    THEN trigger = "play_rainy_playlist"

  输出:
    {
      matched_rule: "rainy_cafe_headphones",
      action: "play_playlist",
      params: {playlist: "rainy_day_essentials", first_track: "Stan"}
    }
```

## 五、执行原子

```
atom_id: system.music-player

输入: {action: "play", track: "Stan", playlist: "rainy_day_essentials"}
输出: {status: "playing", track: "Stan", artist: "Eminem"}

atom_id: system.notification

输入: {title: "下雨天推荐", body: "为你播放《Stan》"}
输出: {status: "sent"}
```

---

## 六、场景串联

```
你走进星巴克, 外面下雨, 戴上耳机:

  system.location     → "星巴克 · 南京西路 · cafe"
  system.weather      → "rain, 18°C"
  system.camera       → "coffee cup detected" (你点了咖啡)
  system.device       → "AirPods connected"
  system.clock        → "Saturday 15:00"
         │
         ▼
  system.context-fusion → "rainy_saturday_cafe + coffee + headphones"
         │
         ▼
  system.rule-engine    → "播放下雨天歌单, 第一首《Stan》"
         │
         ▼
  system.music-player   → 播放《Stan》
  system.notification   → "为你播放下雨天必听的歌"
```

这就是你说的**粒子触发粒子**——不是人手动执行工作流, 是感知原子自动触发决策原子, 决策原子触发执行原子。

---

## 七、需要补的原子清单

```
感知原子 (sensor) — 新增:
  system.location        ← 实时位置 + 地理围栏
  system.camera          ← 物体/场景识别
  system.weather         ← 天气查询
  system.device          ← 蓝牙/WiFi/外设
  system.clock           ← 时间/日期/季节
  system.biometric       ← 心率/压力 (未来)

融合原子 (fusion) — 新增:
  system.context-fusion  ← 多感知融合为情境

决策原子 (rule) — 新增:
  system.rule-engine     ← 情境 → 规则匹配 → 决策

执行原子 (actuator) — 新增:
  system.music-player    ← 播放音频
  system.notification    ← 系统通知
  system.display         ← 屏幕显示
  system.vibrate         ← 震动
```

---

## 八、与现有体系的关系

```
原子分类 v2:

  基础原子 (system.*):
    工具原子 (13个) — 数据处理     ← 已有
    感知原子 (6个)  — 世界输入     ← 新增
    融合原子 (1个)  — 情境理解     ← 新增
    决策原子 (1个)  — 规则匹配     ← 新增
    执行原子 (4个)  — 世界输出     ← 新增

  注册原子 (mcp.*):
    领域原子 (61个) — 外部服务     ← 已有
    终端原子 (未来) — 商品/服务    ← M7 设计
```

---

> **工具原子处理数据。感知原子捕捉世界。融合原子理解情境。决策原子选择动作。执行原子改变世界。**
> **当前的 13 个基础原子全是"工具"。你需要的是后面四类。**
