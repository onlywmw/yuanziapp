# 连接原子实施方案

> **核心**: 连接原子 = 标准原子 + `compatibility` 字段 + 自动匹配
> **原则**: 不新增类型, 不新增接口, 复用现有原子体系

---

## 一、Schema 扩展

在原子 `classification` 或顶层加一个字段：

```json
{
  "atom_id": "connector.location-android",
  "type": "sensor",
  "compatibility": {
    "os": "android",
    "os_version": ">=11",
    "manufacturer": "*",
    "hardware": ["gps"]
  }
}
```

| 字段 | 说明 | 示例 |
|------|------|------|
| os | 操作系统 | android / ios / huawei / windows / linux |
| os_version | 版本约束 | ">=11" / ">=16" |
| manufacturer | 厂商, * = 不限 | "*" / "samsung" / "xiaomi" |
| hardware | 需要的硬件 | ["gps"] / ["bluetooth"] / ["camera"] |

**这个字段加在 `atom-registry-schema.json` 里，不影响现有原子。**

---

## 二、自动匹配

```
用户安装一个工作流, 其中引用了 "获取位置" 功能。

系统执行:
  1. 读本设备的 os + version + manufacturer + hardware
  2. 搜索 type=sensor, function=location
  3. 筛选 compatibility.os == 本设备 os
  4. 按优先级排序:
     · manufacturer 精确匹配 > *
     · 评分高 > 评分低
     · 使用人数多 > 少
  5. 自动安装排第一的

用户不需要手动选。系统自动找到最适合本设备的连接器。
```

## 三、接口标准化

```
同一功能的所有连接器必须实现相同的 I/O Schema:

  "获取位置" (function=location):
    输出: {latitude, longitude, accuracy, timestamp}

    所有 location 连接器——无论 Android、iOS、华为——
    都返回这个结构。上层不关心底层。

标准化方式:
  · 在注册中心注册一个 "接口标准" (type=schema 的原子)
  · connector.location-android 声明: implements="schema.location-v1"
  · 校验: 输出 schema 必须匹配接口标准
```

## 四、实现一个连接器

```
connector.location-android:

  core.py:
    import android.location  ← 调 Android LocationManager
    def handler(data):
        loc = LocationManager.getLastLocation()
        return {
            "status": "success",
            "data": {"latitude": loc.lat, "longitude": loc.lng,
                     "accuracy": loc.accuracy, "timestamp": now()}
        }

  meta.json:
    {
      "atom_id": "connector.location-android",
      "type": "sensor",
      "compatibility": {"os": "android", "hardware": ["gps"]},
      "implements": "schema.location-v1",
      "io": {
        "output": {
          "latitude": "number",
          "longitude": "number",
          "accuracy": "number",
          "timestamp": "string"
        }
      }
    }

  server.py: 标准 /health /meta /run 端点 (和其他原子完全一样)

和普通原子唯一的区别: compatibility 字段。
```

## 五、在 Chaquopy/APK 中的实现

```
连接器本质是调用 Android 系统 API。

在 Chaquopy 环境中:
  Python ←→ Java 互调

  core.py:
    from java import android_location  ← Chaquopy 桥接
    # 或者:
    from chaquopy import android

    def handler(data):
        context = android.getApplicationContext()
        lm = context.getSystemService("location")
        ...
```

## 六、文件变更

```
atom-registry-schema.json    ← + compatibility 字段
DESIGN_ATOM_V2_CLASSIFICATION ← + connector 分类
base-atoms/ 或 connectors/    ← 首批连接器实现
```

## 七、首批实现

```
P0 连接器 (每个平台至少一个):
  connector.location-android       (Android GPS)
  connector.camera-android         (Android CameraX)
  connector.bluetooth-android      (Android BluetoothAdapter)
  connector.storage-android        (Android Storage Access)

P1 连接器:
  connector.location-huawei        (HMS Location)
  connector.music-spotify          (Spotify SDK)
  connector.ai-claude              (Claude API)
```

---

> **连接器就是标准原子 + compatibility。没有新的基础设施, 没有新的类型。复用一切。**
