# 连接原子

> **定位**: 不是造新工具——借用设备已有的能力, 封装为统一接口
> **合并**: DESIGN_CONNECTOR_ATOM + DESIGN_CONNECTOR_IMPLEMENTATION

---

## 一、什么是连接原子

```
普通原子 (造):  自己调 API, 所有平台自己维护
连接原子 (借):  封装平台已有的, 一个平台一个连接器, 接口统一

Android 有 LocationManager → connector.location-android
iPhone 有 CoreLocation    → connector.location-ios
华为有 HMS Location       → connector.location-huawei

对上层来说都叫 "获取位置"。输入输出一样, 底层通路不同。
```

## 二、在原子体系中的位置

连接器不是基础原子, 是注册原子的一种。

```
基础原子 (system.*):
  系统内置, 不可删, 通用逻辑

注册原子:
  ├── 连接器 (connector.*): 平台特定通路, 可安装/删除
  ├── 领域原子 (mcp.*): 数据库、云服务等第三方服务 (也是注册原子)
  └── 终端原子: 商品、服务、作品

连接器 ≠ 基础原子。它是注册原子的子类。
```

## 三、自动匹配

```
用户安装工作流 → 需要"获取位置"
系统: 本设备是 Android → 搜索 connector.location-android → 自动安装
用户不需要手动选。
```

## 四、Schema

```json
{
  "atom_id": "connector.location-android",
  "type": "sensor",
  "compatibility": {
    "os": "android",
    "os_version": ">=11",
    "hardware": ["gps"]
  },
  "implements": "schema.location-v1"
}
```


## 五、不只是硬件

```
连接器不只封装硬件——也封装已有的软件:

  connector.music-spotify    借用 Spotify
  connector.music-apple      借用 Apple Music
  connector.health-samsung   借用三星健康
  connector.ai-claude        借用 Claude
```

---

> **连接器 = 标准原子 + compatibility 字段。不造轮子, 让已有的轮子在 Yuanzi 里转起来。**
