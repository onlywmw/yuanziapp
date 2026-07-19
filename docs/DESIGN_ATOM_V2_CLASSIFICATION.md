# 原子分类体系 v2

> **状态**: `📐 design-ready`
> **作者**: Arch
> **日期**: 2026-07-19
> **变更**: 从单一"工具原子"扩展为五类原子 — 工具/感知/融合/决策/执行

---

## 一、架构变更

```
v1 体系 (当前):
  基础原子 (13个) — 全部是数据处理工具
  注册原子 (61个) — MCP 服务

v2 体系:
  基础原子 (25个):
    工具 (13)  — file-read, http-get, math-calc...
    感知 (6)   — location, camera, weather, device, clock, biometric
    融合 (1)   — context-fusion
    决策 (1)   — rule-engine
    执行 (4)   — music-player, notification, display, vibrate

  注册原子 (61+):
    领域原子 — mcp.* (保持)
    终端原子 — 商品/服务/作品 (M7)
```

## 二、新增原子规格

### 感知类 (sensor)

```
system.location
  类型: sensor
  描述: 实时位置 + 地理围栏
  输入: (无 — 主动采集)
  输出: {latitude, longitude, place, type, accuracy, timestamp}
  触发: 进入/离开地理围栏
  来源: Android LocationManager

system.camera
  类型: sensor
  描述: 物体/场景识别
  输入: (无 — 主动采集)
  输出: {objects[], scene, text, timestamp}
  触发: 检测到特定物体
  来源: Android CameraX + ML Kit

system.weather
  类型: sensor
  描述: 天气查询
  输入: {location}
  输出: {condition, temperature, humidity, forecast}
  触发: 天气变化
  来源: OpenWeather API 或系统天气服务

system.device
  类型: sensor
  描述: 设备状态感知
  输入: (无 — 主动采集)
  输出: {bluetooth[], wifi, battery, screen_on}
  触发: 设备连接/断开
  来源: Android BluetoothAdapter + WifiManager

system.clock
  类型: sensor
  描述: 时间/日期感知
  输入: (无)
  输出: {hour, day, is_weekend, season}
  触发: 特定时间
  来源: System.currentTimeMillis()

system.biometric
  类型: sensor
  描述: 生物特征 (需穿戴设备)
  输入: (无 — 主动采集)
  输出: {heart_rate, stress_level, activity}
  触发: 心率/压力变化
  来源: Wear OS / Health Connect
  状态: 未来实现
```

### 融合类 (fusion)

```
system.context-fusion
  类型: fusion
  描述: 多感知输入 → 单情境输出
  输入: {location, weather, device, camera, clock}
  输出: {situation, mood, tags[], confidence}
  逻辑: 规则加权 + embedding 匹配
```

### 决策类 (rule)

```
system.rule-engine
  类型: rule
  描述: 情境 → 规则匹配 → 动作决策
  输入: {situation, context}
  输出: {matched_rule, action, params{}}
  规则存储: atom_registry 中 type=rule 的原子
```

### 执行类 (actuator)

```
system.music-player
  类型: actuator
  描述: 播放音频
  输入: {action, track, playlist, volume}
  输出: {status, track, artist}
  来源: Android MediaPlayer

system.notification
  类型: actuator
  描述: 系统通知
  输入: {title, body, priority, action}
  输出: {status}
  来源: Android NotificationManager

system.display
  类型: actuator
  描述: 屏幕显示
  输入: {content, layout, duration}
  输出: {status}

system.vibrate
  类型: actuator
  描述: 震动反馈
  输入: {pattern, duration}
  输出: {status}
```

## 三、Schema 变更

`atom-registry-schema.json` 中 `architecture.type` 枚举扩展:

```json
"type": {
  "enum": [
    "function",    ← v1 已有 (工具)
    "external",
    "rule",
    "agent",
    "mcp-server",
    "data",
    "schema",
    "gateway",
    "sensor",      ← v2 新增
    "fusion",      ← v2 新增
    "actuator"     ← v2 新增
  ]
}
```

`classification.category` 新增:

```
"sensor"      - 感知类
"fusion"      - 融合类
"rule"        - 决策类
"actuator"    - 执行类
```

## 四、场景工作流

```
雨天咖啡厅 → 音乐推荐:

  system.location ──┐
  system.weather  ──┤
  system.camera   ──┼──→ system.context-fusion
  system.device   ──┤         │
  system.clock    ──┘         ▼
                        situation: "rainy_cafe_headphones"
                              │
                              ▼
                        system.rule-engine
                              │
                    matched: "rainy_music"
                              │
                              ▼
                        system.music-player → 《Stan》
                        system.notification → "为你播放下雨天的歌"
```

## 五、实施

```
阶段 1: Schema (30 min)
  1. atom-registry-schema.json 扩展 type 枚举
  2. BASE_ATOMS_SPEC.md 补 12 个新原子规格

阶段 2: 基础原子实现 (1天)
  3. base-atoms/ 下新增 12 个原子目录
  4. 每个原子: core.py + server.py + Dockerfile
  5. 测试: test_sensor_atoms.py

阶段 3: 工作流引擎 (1天)
  6. rule-engine 规则存储与匹配
  7. context-fusion 融合逻辑
  8. 端到端场景测试

阶段 4: APK 感知层 (1天)
  9. Android 端实现 location/camera/device/clock 采集
  10. 感知数据流入 context-fusion
```

## 六、文件变更

```
atom-registry-schema.json          ← 扩展 type 枚举
docs/BASE_ATOMS_SPEC.md            ← 补 12 个新原子
base-atoms/location/               ← 新增
base-atoms/camera/                 ← 新增
base-atoms/weather/                ← 新增
base-atoms/device/                 ← 新增
base-atoms/clock/                  ← 新增
base-atoms/context-fusion/         ← 新增
base-atoms/rule-engine/            ← 新增
base-atoms/music-player/           ← 新增
base-atoms/notification/           ← 新增
base-atoms/display/                ← 新增
base-atoms/vibrate/                ← 新增
base-atoms/tests/test_sensors.py   ← 新增
```

---

> **v1: 13 个工具原子 — 只有手, 没有眼睛耳朵。v2: 25 个原子 — 有感知, 有判断, 有动作。**
