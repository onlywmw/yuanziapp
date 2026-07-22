# test_core.py — connector.camera-android 单元测试（hermetic）
#
# 全部测试在 mock 模式（YUANZI_CONNECTOR_MOCK=1，monkeypatch 注入）下运行，
# 验证输出符合 camera I/O 接口标准（schema.camera-v1）：
#   {"image_base64": str, "width": number, "height": number, "timestamp": str}
# 不触碰真实 Android 环境、不访问网络、不依赖外部状态。

import base64
from datetime import datetime

import core
from core import handler

# schema.camera-v1 输出契约：data 的全部键与类型
CAMERA_KEYS = {"image_base64", "width", "height", "timestamp"}


def _assert_io_standard(result):
    """校验 handler 输出严格符合 camera I/O 标准。"""
    assert result["status"] == "success"
    data = result["data"]
    assert set(data.keys()) == CAMERA_KEYS
    assert isinstance(data["image_base64"], str)
    assert isinstance(data["width"], (int, float))
    assert isinstance(data["height"], (int, float))
    assert isinstance(data["timestamp"], str)
    return data


def test_mock_returns_success(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    result = handler({})
    assert result["status"] == "success"
    assert "data" in result


def test_mock_output_matches_io_standard(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    _assert_io_standard(handler({}))


def test_mock_data_is_realistic(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    data = _assert_io_standard(handler({}))
    # 逼真性：image_base64 可解码为合法 PNG（魔数校验），宽高为正，时间戳可解析
    raw = base64.b64decode(data["image_base64"])
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert data["width"] > 0
    assert data["height"] > 0
    datetime.fromisoformat(data["timestamp"])


def test_mock_image_payload_deterministic_across_calls(monkeypatch):
    """图像内容（base64 与宽高）在多次调用间确定；时间戳随调用更新。"""
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    a = handler({})["data"]
    b = handler({})["data"]
    assert a["image_base64"] == b["image_base64"]
    assert (a["width"], a["height"]) == (b["width"], b["height"])


def test_none_and_empty_input(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    _assert_io_standard(handler(None))
    _assert_io_standard(handler({}))


def test_mock_ignores_lens_option(monkeypatch):
    """mock 模式下 lens 入参可选且被忽略，输出仍符合接口标准。"""
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    _assert_io_standard(handler({"lens": "front"}))
    _assert_io_standard(handler({"lens": "back"}))


def test_unsupported_platform_without_mock(monkeypatch):
    """桌面/非 Android 环境且无 mock：必须返回 unsupported_platform。"""
    monkeypatch.delenv("YUANZI_CONNECTOR_MOCK", raising=False)
    if core._is_android():
        # 真 Android 环境不走此分支（CI/桌面才会执行到）
        return
    result = handler({})
    assert result["status"] == "error"
    assert result["error"]["code"] == "unsupported_platform"


def test_module_imports_without_java_bridge():
    """桌面环境无 Chaquopy java 桥接时模块可导入不崩，桥接降级为不可用。"""
    assert hasattr(core, "handler")
    if not core._is_android():
        assert core._HAS_CHAQUOPY is False or core.jclass is None
