# 感知原子保活策略

> **原则**: 不是所有感知都需要持续。按电池成本分级。

---

## 一、分级策略

```
L0 零成本 (系统广播, 不轮询):
  device (蓝牙/WiFi)    → BroadcastReceiver, 设备连接时系统主动通知
  clock (时间)          → AlarmManager, 到点唤醒

L1 低成本 (低频轮询, 30min+):
  weather (天气)        → WorkManager, 30 分钟一次
  location (位置)       → Geofencing, 进出区域时系统通知

L2 中成本 (前台服务, 按需开启):
  持续模式感知原子       → Foreground Service + 通知栏常驻

L3 高成本 (仅在 App 前台):
  camera (摄像头)       → 不开后台, 电池扛不住
```

## 二、前台服务保活

```
需要持续监测的原子 (如多个 L2 感知):

  McpService (已有) → 前台服务
    · 通知栏: "Yuanzi 正在感知环境"
    · 用户可一键关闭 (通知栏按钮)
    · 系统杀进程概率低 (前台服务优先级高)

  Foreground Service 是 Android 最可靠的保活方式。
  因为用户看得见, 系统不敢随便杀。
```

## 三、不是所有原子都需要保活

```
多数场景不需要持续:

  咖啡厅场景:
    location → Geofencing (进咖啡厅时系统通知, 不轮询)
    weather  → WorkManager (30min 一次, 够用)
    device   → BroadcastReceiver (蓝牙连接时通知, 零成本)
    camera   → 用户打开 App 时触发 (不进后台)

  没有一个原子需要 24/7 持续运行。
  都是用 Android 系统机制触发, 不自己轮询。
```

## 四、感知原子如何注册保活

```
原子声明:

{
  "atom_id": "connector.location-android",
  "keepalive": {
    "strategy": "geofencing",      ← 不是 polling
    "regions": ["home", "cafe"],
    "cost": "L1"
  }
}

{
  "atom_id": "connector.device-android",
  "keepalive": {
    "strategy": "broadcast",        ← 系统通知
    "actions": ["BLUETOOTH_CONNECTED", "BLUETOOTH_DISCONNECTED"],
    "cost": "L0"
  }
}
```

## 五、用户控制

```
用户可随时关闭感知:

  通知栏: [停止感知] → 所有持续模式原子停止
  设置页: 每个感知原子独立开关
  省电模式: 自动降级 L1/L2 → L0
```
