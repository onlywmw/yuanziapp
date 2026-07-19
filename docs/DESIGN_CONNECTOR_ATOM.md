# 连接原子

> **定位**: 不是造新工具——是借用设备已有的能力, 封装为统一接口
> **问题**: 同一功能在不同设备上通路不同, 不能为每种设备造一套原子

---

## 一、什么是连接原子

```
普通原子 (造):
  system.weather → 自己调天气 API

连接原子 (借):
  connector.weather → 借用手机自带天气服务

区别:
  造: 从零实现, 所有平台自己维护
  借: 封装平台已有的, 一个平台一个连接器, 接口统一
```

## 二、为什么需要

```
同一个功能在不同设备上走不同的通路:

  "获取位置":
    Android → LocationManager (Google)
    iPhone  → CoreLocation (Apple)
    华为    → HMS Location (华为)
    小米    → Mi Location (小米)

  如果为每种设备各造一个原子:
    · 61 个注册原子 → 可能变成 200 个
    · 作者不知道用户用什么设备
    · 用户安装后还得手动选"哪个版本适合我"

  连接原子的做法:
    · 只有一个原子: "获取位置"
    · 接口统一: 输入 {precision}, 输出 {lat, lng}
    · 安装时自动选择匹配的连接器
    · 用户不用管底层是什么
```

## 三、在原子体系中的位置

```
连接器不是基础原子, 是注册原子的一种。

  基础原子 (system.*):
    系统内置, 不可删, 随系统升级
    通用逻辑, 无平台差异 (math-calc, string-split)

  注册原子:
    ├── 连接器 (connector.*): 平台通路, 有作者, 可安装/删除
    │     connector.location-android, connector.camera-ios ...
    ├── 领域原子 (mcp.*): 数据库、云服务
    └── 终端原子: 商品、服务、作品

区别:
  基础原子 = 地基, 不可拆
  连接器 = 插座, 不同墙不同插座, 但接口一样
```

## 四、连接原子示例

```
connector.location-android    封装 Android LocationManager
connector.location-ios        封装 iOS CoreLocation
connector.location-huawei     封装华为 HMS Location

它们都实现了同一个接口:
  output: {latitude, longitude, accuracy, timestamp}

connector.camera-android      封装 Android CameraX
connector.camera-ios          封装 iOS AVFoundation

  output: {image_base64, width, height, timestamp}

connector.bluetooth-android   封装 Android BluetoothAdapter
connector.bluetooth-ios       封装 iOS CoreBluetooth

  output: {devices: [{name, id, connected}]}

connector.storage-android     封装 Android Storage Access
connector.storage-ios         封装 iOS FileManager

  output: {files: [{name, path, size}]}
```

## 五、连接器如何被选择

```
用户安装一个工作流, 其中需要 "获取位置":

  系统检查:
    本设备是 Android → 搜索 connector.location-android
    本设备是 iPhone → 搜索 connector.location-ios

  自动安装匹配的连接器。用户不需要手动选。

如果某个平台没有连接器:
  → 提示 "此工作流需要获取位置, 但你当前的设备没有对应的连接器"
  → 不阻止使用, 但工作流中该节点标记为 "不可用"
```

## 六、连接器市场

```
连接器也是原子。在市场中筛选 type=connector:

  connector.location-android     作者: Google · 1.2M 人使用
  connector.location-ios         作者: Apple · 980K 人使用
  connector.location-huawei      作者: 华为社区 · 320K 人使用
  connector.bluetooth-universal  作者: 张三 · 128K 人使用 · ⭐4.8

作者可以为特定平台贡献连接器。
一个好的连接器让同一功能在所有平台上都能用。
```

## 七、借力——不只是硬件

```
连接原子不只封装硬件——也封装已有的软件能力:

  connector.music-spotify     借用 Spotify 播放音乐
  connector.music-apple       借用 Apple Music
  connector.health-samsung    借用三星健康
  connector.health-apple      借用 Apple Health
  connector.weather-openweather 借用 OpenWeather API
  connector.weather-accuweather 借用 AccuWeather
  connector.ai-chatgpt        借用 ChatGPT
  connector.ai-claude         借用 Claude

不是自己造一个音乐播放器。
是连接已有的音乐服务。
```

---

## 八、实施

```
P0:
  · connector 类型加入原子分类体系 (DESIGN_ATOM_V2_CLASSIFICATION)
  · 接口标准: 每个连接器功能必须有统一的 I/O Schema

P1:
  · 平台检测: 安装工作流时自动匹配连接器
  · 首批连接器: location/camera/bluetooth/storage (Android)

P2:
  · 软件服务连接器: music/health/weather/ai
  · 社区贡献指南: 如何为你的平台写连接器
```

---

> **造工具是埋头苦干。借力是抬头看路。连接原子不造轮子, 它让已有的轮子在 Yuanzi 里转起来。**
