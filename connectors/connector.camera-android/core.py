# core.py — connector.camera-android Android 相机连接器（连接原子，implements schema.camera-v1）
"""Android 相机连接原子。

借用设备已有的相机能力（Android CameraX），输出统一遵循 schema.camera-v1 接口标准：
    {"image_base64": str, "width": number, "height": number, "timestamp": str}

运行形态：
  · 真实 Android（Chaquopy 内嵌解释器）→ 走 CameraX 桥接采集；
  · 非 Android 环境 → 返回 unsupported_platform 错误；
  · 任意环境设置 YUANZI_CONNECTOR_MOCK=1 → 返回符合接口标准的 mock 数据（开发/测试用）。
"""
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Chaquopy Java 桥接（容错导入：桌面 / CI 环境必须可导入本模块而不崩溃）。
#
# 真实 Android 路径的 CameraX 桥接思路：
#   1. 本模块运行在 Chaquopy 内嵌于 Android App 进程的 Python 解释器中；
#   2. 通过 `from java import jclass` 拿到 Java 类引用，由 Android 壳层
#      （Activity / Service）注入应用 Context 与相机桥对象；
#   3. CameraX 以 ProcessCameraProvider 绑定相机生命周期，拍照时调用
#      androidx.camera.core.ImageCapture.takePicture()，在回调中取得内存中的
#      JPEG/PNG 字节（无需落盘）；
#   4. 字节经 base64 编码后，与实际宽高、时间戳组成 schema.camera-v1 标准输出。
#   相机权限（android.permission.CAMERA）由壳层在调用前向用户申请。
# ---------------------------------------------------------------------------
try:
    from java import jclass  # type: ignore  # 仅 Chaquopy / Android 环境存在

    _HAS_CHAQUOPY = True
except Exception:  # ImportError 等：桌面 / CI / 服务器环境
    jclass = None
    _HAS_CHAQUOPY = False

MOCK_ENV_VAR = "YUANZI_CONNECTOR_MOCK"

# mock 模式返回的占位图像：1x1 像素透明 PNG（68 字节）的 base64。
_MOCK_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII="
)
_MOCK_IMAGE_WIDTH = 1
_MOCK_IMAGE_HEIGHT = 1


def _now_iso() -> str:
    """UTC ISO 8601 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def _is_mock_mode() -> bool:
    return os.environ.get(MOCK_ENV_VAR) == "1"


def _is_android() -> bool:
    """是否运行在真实 Android 环境（Chaquopy 桥可用或解释器带 android API level）。"""
    return _HAS_CHAQUOPY or hasattr(sys, "getandroidapilevel")


def _unsupported_platform():
    return {
        "status": "error",
        "error": {
            "code": "unsupported_platform",
            "message": "connector.camera-android 仅支持 Android 设备；"
            f"当前环境非 Android（可设置 {MOCK_ENV_VAR}=1 使用 mock 数据）",
        },
    }


def _mock_capture():
    """开发/测试用的逼真 mock 数据，字段与类型严格符合 schema.camera-v1 输出契约。"""
    return {
        "image_base64": _MOCK_IMAGE_BASE64,
        "width": _MOCK_IMAGE_WIDTH,
        "height": _MOCK_IMAGE_HEIGHT,
        "timestamp": _now_iso(),
    }


def _capture_android(data):
    """真实 CameraX 采集路径，仅在 Android / Chaquopy 环境可达（桌面不会进入）。"""
    if not _HAS_CHAQUOPY:
        # handler 已先做平台判断，此处仅为防御，正常不可达。
        return _unsupported_platform()
    lens = (data or {}).get("lens", "back")
    # --- CameraX 桥接（真实实现依赖 Android 壳层注入的 Java 桥对象） ---
    # bridge = jclass("app.yuanzi.bridge.CameraBridge")   # 壳层提供的 Java 桥
    # shot = bridge.capture(lens)                         # 触发 ImageCapture.takePicture()
    # image_bytes = bytes(shot.getBytes())                # 内存中的 JPEG/PNG 字节
    # import base64
    # return {
    #     "status": "success",
    #     "data": {
    #         "image_base64": base64.b64encode(image_bytes).decode("ascii"),
    #         "width": int(shot.getWidth()),
    #         "height": int(shot.getHeight()),
    #         "timestamp": _now_iso(),
    #     },
    # }
    raise RuntimeError(
        "camera bridge not available：需要 Android 壳层注入 CameraX 桥对象 "
        f"(lens={lens!r})；开发/测试请设置 {MOCK_ENV_VAR}=1"
    )


def handler(data):
    """
    拍摄一张照片，输出遵循 schema.camera-v1 接口标准：
        {"image_base64": str, "width": number, "height": number, "timestamp": str}

    :param data: {} 或 {"lens": "back"|"front"}（均可选；mock 模式下忽略）
    :return: {"status": "success", "data": {...}} 或
             {"status": "error", "error": {"code": ..., "message": ...}}
    """
    try:
        if _is_mock_mode():
            return {"status": "success", "data": _mock_capture()}
        if not _is_android():
            return _unsupported_platform()
        return _capture_android(data or {})
    except Exception as e:
        return {"status": "error", "error": {"code": "capture_failed", "message": str(e)}}
