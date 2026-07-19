# 原子目录

> **定位**: 所有原子的完整清单 — 从 13 个工具原子到 12 个感知/融合/决策/执行原子
> **合并**: BASE_ATOMS_SPEC + ATOM_SENSOR_LAYER

---

## 一、工具原子 (13)

```
file-dir       文件夹操作
file-read      文件读取
file-write     文件写入
http-get       HTTP GET
http-post      HTTP POST
math-calc      数学运算
string-split   字符串拆分
string-match   正则匹配
json-parse     JSON 解析
date-time      日期时间
hash-digest    哈希计算
encrypt-aes    AES 加密
decrypt-aes    AES 解密
```

## 二、感知原子 (6)

```
location       实时位置 + 地理围栏
camera         物体/场景识别
weather        天气查询
device         设备状态 (蓝牙/WiFi)
clock          时间/日期
biometric      生物特征 (未来)
```

## 三、融合原子 (1)

```
context-fusion 多感知→单情境
```

## 四、决策原子 (1)

```
rule-engine    情境→规则匹配→决策
```

## 五、执行原子 (4)

```
music-player   播放音频
notification   系统通知
display        屏幕显示
vibrate        震动反馈
```

## 六、AI 原子 (1)

```
system.ai      本地 ONNX 意图理解
```

## 七、连接原子 (注册原子的子类, 首批)

```
connector.location-android    Android GPS
connector.camera-android      Android CameraX
connector.bluetooth-android   Android Bluetooth
connector.storage-android     Android Storage
connector.tts-android         Android TTS
connector.music-spotify       Spotify
```

## 八、领域原子示例 (mcp.*, 注册原子, 61+)

```
mcp.postgres    PostgreSQL 数据库
mcp.mysql       MySQL 数据库
mcp.s3          云存储
mcp.iam         权限管理
... (61 个)
```

## 九、人原子 (1)

```
person-atom    系统中最丰富的场。两层档案。
```

---

> **28 个原子 · 6 类 · 工具/感知/融合/决策/执行/连接 + AI + 人**
