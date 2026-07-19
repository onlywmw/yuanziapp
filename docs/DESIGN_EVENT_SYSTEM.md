# 原子事件系统

> **问题**: 原子只会等人调用。咖啡厅场景需要原子自己感知、自己触发。
> **方案**: 感知原子持续运行 → 变化时发出事件 → 融合原子订阅 → 决策触发执行

---

## 一、现在的原子 vs 需要的原子

```
现在 (被动):
  人打开 App → 手动触发 workflow → atom.handler(data) → 返回结果

需要 (主动):
  天气变了 → 自动发出事件 → fusion 收到 → 条件满足 → 自动播歌
  人什么都没做。
```

## 二、事件驱动

```
每个感知原子有两种运行模式:

  按需模式 (现在):
    被工作流调用 → 采集一次 → 返回结果 → 结束

  持续模式 (新增):
    后台运行 → 定期采集 → 数据变化超过阈值 → 发出事件
```

```
事件格式:

{
  "source": "system.weather",
  "event": "changed",
  "data": {"condition": "rain", "previous": "cloudy"},
  "timestamp": "..."
}

{
  "source": "system.device",
  "event": "connected", 
  "data": {"device": "AirPods Pro"},
  "timestamp": "..."
}
```

## 三、工作流激活

```
一个工作流声明为"自动":

{
  "workflow_id": "coffee_shop_music",
  "activation": "auto",           ← 自动, 不是 manual
  "trigger": {
    "conditions": [
      {"source": "system.weather", "event": "changed", "condition": "rain"},
      {"source": "system.device", "event": "connected", "device_type": "headphones"},
      {"source": "system.location", "event": "entered", "place_type": "cafe"}
    ],
    "logic": "all"                 ← 所有条件都满足才触发
  }
}
```

## 四、执行流程

```
1. 工作流声明 auto 模式 → 注册到事件总线
2. 感知原子持续运行 → 发出事件
3. 事件总线收到事件 → 检查所有 auto 工作流的触发条件
4. 条件满足 → 工作流自动执行

咖啡厅场景:

  system.weather → "rain" (事件)
  system.location → "entered cafe" (事件)
  system.camera → "coffee cup detected" (事件)
  system.device → "headphones connected" (事件)
       ↓
  事件总线累积事件
       ↓
  coffee_shop_music 条件全部满足
       ↓
  自动触发 workflow → fusion → decision → 《Stan》
```

## 五、实现

```
事件总线:
  · 内存中的 event queue (同一设备, 不用消息队列)
  · 每个 auto 工作流有 trigger 条件
  · 收到事件 → 匹配条件 → 触发

感知原子后台运行:
  · Android WorkManager / AlarmManager 定期唤醒
  · 或者前台 Service 持续监听 (GPS/蓝牙)

零新增基础设施:
  · 事件总线和当前 GraphStore 可以合并
  · 感知原子就是标准原子 + 一个 schedule
```
