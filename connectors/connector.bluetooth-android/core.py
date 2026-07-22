# core.py — connector.bluetooth-android 蓝牙连接器（连接原子）
#
# 实现接口标准 schema.bluetooth-v1（implements）：
#   输出契约：{"devices": [{"name": str, "id": str, "connected": bool}, ...]}
#
# 真实路径（Android / Chaquopy 运行时）的桥接思路：
#   Chaquopy 在 Python 进程内注入 `java` 桥接模块，用 `from java import jclass`
#   直接拿到 Java 类并调用 Android 系统 API：
#     1. 取应用上下文：
#          context = jclass("com.chaquo.python.Python").getPlatform().getApplication()
#     2. bt_manager = context.getSystemService("bluetooth")   # BluetoothManager
#     3. adapter    = bt_manager.getAdapter()                 # BluetoothAdapter
#     4. adapter.isEnabled() 检查蓝牙开关
#     5. adapter.getBondedDevices() 枚举已配对设备（java.util.Set<BluetoothDevice>）
#     6. 每台设备：getName() / getAddress()；连接态公开 API 不直接暴露，
#        标准做法是注册 BluetoothProfile.ServiceListener 代理（A2DP/HEADSET/GATT）
#        逐项查询，这里用隐藏方法 isConnected() 反射兜底，失败按未连接处理。
#   Android 12+（API 31+）枚举/连接蓝牙需要运行时权限 BLUETOOTH_CONNECT，
#   已在 meta.json 的 compliance.permissions_required 中声明。
#
# 非 Android 环境（桌面/CI）：
#   `from java import jclass` import 失败属预期，模块仍可正常导入不崩；
#   handler 走真实路径时返回 {"status":"error","error":{"code":"unsupported_platform",...}}。
#   开发/测试设环境变量 YUANZI_CONNECTOR_MOCK=1，返回符合 I/O 标准的逼真 mock 数据。

import os
import sys

# --- Chaquopy Java 桥接：仅 Android 运行时可用，桌面 import 失败不崩 ---
try:
    from java import jclass  # type: ignore  # Chaquopy 运行时注入的桥接入口

    _JAVA_OK = True
except Exception:  # ImportError 及桥接层任何初始化异常一律容错
    jclass = None
    _JAVA_OK = False

# Chaquopy 会注入 ANDROID_PRIVATE / ANDROID_ARGUMENT 等环境变量；
# sys.platform == "android" 作为补充判定。
_IS_ANDROID = _JAVA_OK and (
    sys.platform == "android"
    or "ANDROID_PRIVATE" in os.environ
    or "ANDROID_ARGUMENT" in os.environ
)


def _mock_enabled():
    """调用时读取环境变量，便于测试用 monkeypatch 切换。"""
    return os.environ.get("YUANZI_CONNECTOR_MOCK") == "1"


def _mock_devices():
    """符合 bluetooth I/O 标准的逼真 mock 数据（2-3 台假设备）。"""
    return [
        {"name": "Sony WH-1000XM5", "id": "00:1A:7D:DA:71:13", "connected": True},
        {"name": "Logitech MX Keys Mini", "id": "DC:2C:26:0B:5F:8E", "connected": False},
        {"name": "Xiaomi Mi Band 8", "id": "F8:4E:73:2A:9C:01", "connected": False},
    ]


def _get_android_context():
    """取 Android Application 上下文（Chaquopy 标准入口）。"""
    python_cls = jclass("com.chaquo.python.Python")
    return python_cls.getPlatform().getApplication()


def _is_connected(dev):
    """查询设备连接态。

    公开 API 没有直接的 isConnected：标准做法是注册
    BluetoothProfile.ServiceListener 代理（A2DP/HEADSET/GATT 等 profile）
    再逐项查询；此处先用蓝牙类隐藏方法 isConnected() 反射兜底，
    反射失败按未连接处理，保证枚举不中断。
    """
    try:
        method = dev.getClass().getMethod("isConnected")
        return bool(method.invoke(dev))
    except Exception:
        return False


def _list_devices_real():
    """真实 Android 路径：BluetoothAdapter.getBondedDevices() 枚举已配对设备。"""
    context = _get_android_context()
    bt_manager = context.getSystemService("bluetooth")
    adapter = bt_manager.getAdapter()
    if adapter is None:
        raise RuntimeError("no_bluetooth_adapter")
    if not adapter.isEnabled():
        raise RuntimeError("bluetooth_disabled")
    bonded = adapter.getBondedDevices()  # java.util.Set<BluetoothDevice>
    devices = []
    for dev in bonded.toArray():
        devices.append(
            {
                "name": dev.getName() or "",
                "id": dev.getAddress(),
                "connected": _is_connected(dev),
            }
        )
    return devices


def handler(data):
    """
    枚举蓝牙设备，输出符合 schema.bluetooth-v1 接口标准。
    :param data: {"connected_only": false}  # connected_only 可选，为 true 时只返回已连接设备
    """
    data = data or {}
    connected_only = bool(data.get("connected_only"))

    if _mock_enabled():
        devices = _mock_devices()
        if connected_only:
            devices = [d for d in devices if d["connected"]]
        return {"status": "success", "data": {"devices": devices}}

    if not _IS_ANDROID:
        return {
            "status": "error",
            "error": {
                "code": "unsupported_platform",
                "message": "connector.bluetooth-android 仅支持 Android 运行时"
                "（Chaquopy Java 桥接）；当前平台不可用。"
                "开发/测试请设 YUANZI_CONNECTOR_MOCK=1。",
            },
        }

    try:
        devices = _list_devices_real()
        if connected_only:
            devices = [d for d in devices if d["connected"]]
        return {"status": "success", "data": {"devices": devices}}
    except Exception as e:
        msg = str(e)
        if "no_bluetooth_adapter" in msg:
            code = "bluetooth_unavailable"
        elif "bluetooth_disabled" in msg:
            code = "bluetooth_disabled"
        else:
            code = "bluetooth_error"
        return {"status": "error", "error": {"code": code, "message": msg}}
