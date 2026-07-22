# test_core.py — connector.location-android 单元测试（hermetic）
#
# 全部测试在 mock 模式（YUANZI_CONNECTOR_MOCK=1，monkeypatch 注入）下运行，
# 验证输出符合 location I/O 接口标准：
#   {"latitude": number, "longitude": number, "accuracy": number, "timestamp": str}
# 不触碰真实 Android 环境、不访问网络、不依赖外部状态。

from datetime import datetime

import core
from core import handler

# schema.location-v1 输出契约：全部键与类型
LOCATION_KEYS = {"latitude", "longitude", "accuracy", "timestamp"}


def _is_number(x):
    # bool 是 int 子类，必须排除
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _assert_io_standard(result):
    """校验 handler 输出严格符合 location I/O 标准。"""
    assert result["status"] == "success"
    loc = result["data"]
    assert set(loc.keys()) == LOCATION_KEYS
    assert _is_number(loc["latitude"])
    assert _is_number(loc["longitude"])
    assert _is_number(loc["accuracy"])
    assert isinstance(loc["timestamp"], str)
    return loc


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
    loc = _assert_io_standard(handler({}))
    # 逼真性：经纬度在合法范围内、精度为正、时间戳可解析为 ISO 8601
    assert -90.0 <= loc["latitude"] <= 90.0
    assert -180.0 <= loc["longitude"] <= 180.0
    assert loc["accuracy"] > 0
    datetime.fromisoformat(loc["timestamp"])


def test_mock_deterministic_across_calls(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    assert handler({}) == handler({})


def test_none_and_empty_input(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    _assert_io_standard(handler(None))
    _assert_io_standard(handler({}))


def test_optional_provider_input_accepted(monkeypatch):
    """可选 provider 输入被接受且不破坏输出契约（mock 模式下忽略其取值）。"""
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    _assert_io_standard(handler({"provider": "network"}))


def test_unsupported_platform_without_mock(monkeypatch):
    """桌面/非 Android 环境且无 mock：必须返回 unsupported_platform。"""
    monkeypatch.delenv("YUANZI_CONNECTOR_MOCK", raising=False)
    if core._IS_ANDROID:
        # 真 Android 环境不走此分支（CI/桌面才会执行到）
        return
    result = handler({})
    assert result["status"] == "error"
    assert result["error"]["code"] == "unsupported_platform"


def test_module_imports_without_java_bridge():
    """桌面环境无 Chaquopy java 桥接时模块可导入不崩，桥接降级为不可用。"""
    assert hasattr(core, "handler")
    if not core._IS_ANDROID:
        assert core._JAVA_OK is False or core.jclass is None
