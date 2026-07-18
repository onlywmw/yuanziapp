# Widget MCP Android 客户端

这是 Yuanzi 原子生态的 Android 前端，负责在平板上展示原子知识图谱并调用 Yuanzi 核心服务。

## 依赖准备

本目录下的二进制 jar 文件**不包含在 git 仓库中**，首次构建前需要手动准备。

### 1. android.jar

从本地 Android SDK 复制：

```bash
# 典型路径示例
ANDROID_SDK/platforms/android-34/android.jar
```

复制到本目录：

```bash
cp $ANDROID_SDK/platforms/android-34/android.jar widgetmcp_src/android.jar
```

最低支持 API 28（Android 9.0）。

### 2. Kotlin 标准库

下载 `kotlin-stdlib-1.9.20.jar`：

```bash
mkdir -p widgetmcp_src/libs
curl -L -o widgetmcp_src/libs/kotlin-stdlib-1.9.20.jar \
  https://repo1.maven.org/maven2/org/jetbrains/kotlin/kotlin-stdlib/1.9.20/kotlin-stdlib-1.9.20.jar
```

### 3. NanoHTTPD

下载 `nanohttpd-2.3.1.jar`：

```bash
curl -L -o widgetmcp_src/libs/nanohttpd-2.3.1.jar \
  https://repo1.maven.org/maven2/org/nanohttpd/nanohttpd/2.3.1/nanohttpd-2.3.1.jar
```

## 构建

```bash
cd widgetmcp_src
sh build.sh
```

构建产物为 `widgetmcp.apk`，位于当前目录。

## 安装到平板

```bash
sh build_adb.sh
```

该脚本会先编译 APK，然后通过 adb 安装到已连接的 Android 设备。

## 与 Yuanzi 后端的连接

客户端默认连接：

```
Yuanzi Core: http://127.0.0.1:8080
```

如需修改，编辑：

```
java/com/nous/widgetmcp/yuanzi/YuanziConfig.kt
```

## 核心模块

| 模块 | 说明 |
|------|------|
| `yuanzi/` | 与 Yuanzi Core 通信：拉取图谱、同步状态 |
| `ui/` | 自定义 View：图谱节点、连线渲染 |
| `widget/` | Android 桌面小组件 |
| `browser/` | 内置浏览器，执行 browser 类原子命令 |

## 注意

- 客户端需要 Yuanzi Core（端口 8080）已启动才能正常显示图谱。
- 桌面小组件需要在系统设置中手动添加。
