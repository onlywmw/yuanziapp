# core.py — connector.location-android 位置连接器（连接原子）
#
# 实现接口标准 schema.location-v1（implements）：
#   输出契约：{"latitude": number, "longitude": number, "accuracy": number, "timestamp": str}
#
# 真实路径（Android / Chaquopy 运行时）的桥接思路：
#   Chaquopy 在 Python 进程内注入 `java` 桥接模块，用 `from java import jclass`
#   直接拿到 Java 类并调用 Android 系统 API：
#     1. 取应用上下文：
#          context = jclass("com.chaquo.python.Python").getPlatform().getApplication()
#     2. lm = context.getSystemService("location")        # LocationManager
#     3. lm.isProviderEnabled(provider) 检查 GPS/网络定位开关
#     4. loc = lm.getLastLocation(provider)               # 最近缓存定位，可能为 None
#        —— 工业界更推荐 FusedLocationProviderClient.getLastLocation()（Google Play
#        服务，省电且融合多源），或 LocationManager.requestSingleUpdate() 主动拉新
#        定位；本连接器先用系统 LocationManager.getLastLocation 这一无回调的最简
#        路径，返回 None 时降级遍历其他已启用 provider（gps → network → passive）。
#     5. loc.getLatitude() / getLongitude() / getAccuracy()（米）/ getTime()
#        （UTC 毫秒）→ 转 ISO 8601 字符串。
#   定位需要运行时权限 ACCESS_FINE_LOCATION / ACCESS_COARSE_LOCATION，
#   已在 meta.json 的 compliance.permissions_required 中声明。
#
# 非 Android 环境（桌面/CI）：
#   `from java import jclass` import 失败属预期，模块仍可正常导入不崩；
#   handler 走真实路径时返回 {"status":"error","error":{"code":"unsupported_platform",...}}。
#   开发/测试设环境变量 YUANZI_CONNECTOR_MOCK=1，返回符合 I/O 标准的逼真 mock 数据。

import os
import sys
from datetime import datetime, timezone

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


def _mock_location():
    """符合 location I/O 标准的逼真 mock 数据。

    北京中关村某处的固定快照（固定时间戳保证多次调用确定性）。
    """
    return {
        "latitude": 39.9847,
        "longitude": 116.3065,
        "accuracy": 18.0,
        "timestamp": "2026-07-19T10:24:36+08:00",
    }


def _get_android_context():
    """取 Android Application 上下文（Chaquopy 标准入口）。"""
    python_cls = jclass("com.chaquo.python.Python")
    return python_cls.getPlatform().getApplication()


def _iso_from_epoch_millis(millis):
    """Android Location.getTime() 返回 UTC 毫秒，转 ISO 8601 字符串。"""
    return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc).isoformat()


def _get_location_real(provider):
    """真实 Android 路径：LocationManager.getLastLocation 取最近定位。"""
    context = _get_android_context()
    lm = context.getSystemService("location")  # android.location.LocationManager
    if lm is None:
        raise RuntimeError("no_location_manager")
    # 优先请求的 provider（默认 gps），不可用/无缓存时降级遍历常见 provider
    candidates = [provider] + [p for p in ("gps", "network", "passive") if p != provider]
    loc = None
    for name in candidates:
        try:
            if lm.isProviderEnabled(name):
                loc = lm.getLastLocation(name)
        except Exception:
            loc = None
        if loc is not None:
            break
    if loc is None:
        raise RuntimeError("location_unavailable")
    return {
        "latitude": float(loc.getLatitude()),
        "longitude": float(loc.getLongitude()),
        "accuracy": float(loc.getAccuracy()),
        "timestamp": _iso_from_epoch_millis(int(loc.getTime())),
    }


def handler(data):
    """
    获取设备当前位置，输出符合 schema.location-v1 接口标准。
    :param data: {"provider": "gps"}  # provider 可选，默认 gps；mock 模式下忽略
    """
    data = data or {}
    provider = str(data.get("provider") or "gps")

    if _mock_enabled():
        return {"status": "success", "data": _mock_location()}

    if not _IS_ANDROID:
        return {
            "status": "error",
            "error": {
                "code": "unsupported_platform",
                "message": "connector.location-android 仅支持 Android 运行时"
                "（Chaquopy Java 桥接）；当前平台不可用。"
                "开发/测试请设 YUANZI_CONNECTOR_MOCK=1。",
            },
        }

    try:
        return {"status": "success", "data": _get_location_real(provider)}
    except Exception as e:
        msg = str(e)
        if "no_location_manager" in msg or "location_unavailable" in msg:
            code = "location_unavailable"
        elif "SecurityException" in msg or "permission" in msg.lower():
            code = "permission_denied"
        else:
            code = "location_error"
        return {"status": "error", "error": {"code": code, "message": msg}}
