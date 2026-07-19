# TTS 连接原子

> **定位**: 封装 Android 内置 TTS, 零模型, 零延迟, 离线可用
> **类型**: connector (执行)

---

## 原子定义

```
atom_id:     connector.tts-android
类型:        actuator
描述:        调用 Android TextToSpeech, 将文字转为语音输出
输入:        {text: "为你播放《Stan》", language: "zh-CN", rate: 1.0}
输出:        {status: "spoken"}
延迟:        < 50ms (引擎初始化后)
依赖:        Android TextToSpeech API (系统内置)
离线:        是 (已下载语言包)
```

## 使用场景

```
工作流未尾:
  rule-engine → connector.tts-android
  执行结果 → 语音播报

不需要屏幕, 不需要看。
戴上耳机, 直接听到结果。
```

## 约束

```
· 语言包首次使用前需下载 (系统自动)
· 短文本 (< 500 字) 直接播, 长文本分段
· 失败不阻塞工作流 (容错策略=skip)
```
