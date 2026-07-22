# test_core.py — connector.bluetooth-android 单元测试（hermetic）
#
# 全部测试在 mock 模式（YUANZI_CONNECTOR_MOCK=1，monkeypatch 注入）下运行，
# 验证输出符合 bluetooth I/O 接口标准：
#   {"devices": [{"name": str, "id": str, "connected": bool}, ...]}
# 不触碰真实 Android 环境、不访问网络、不依赖外部状态。

import core
from core import handler

# schema.bluetooth-v1 输出契约：devices 数组元素的全部键与类型
DEVICE_KEYS = {"name", "id", "connected"}


def _assert_io_standard(result):
    """校验 handler 输出严格符合 bluetooth I/O 标准。"""
    assert result["status"] == "success"
    devices = result["data"]["devices"]
    assert isinstance(devices, list)
    for d in devices:
        assert set(d.keys()) == DEVICE_KEYS
        assert isinstance(d["name"], str)
        assert isinstance(d["id"], str)
        assert isinstance(d["connected"], bool)
    return devices


def test_mock_returns_success(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    result = handler({})
    assert result["status"] == "success"
    assert "data" in result


def test_mock_output_matches_io_standard(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    devices = _assert_io_standard(handler({}))
    # mock 数据为 2-3 台假设备
    assert 2 <= len(devices) <= 3


def test_mock_data_is_realistic(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    devices = _assert_io_standard(handler({}))
    # 逼真性：有已连接也有未连接设备，id 形如 MAC 地址
    assert any(d["connected"] for d in devices)
    assert any(not d["connected"] for d in devices)
    for d in devices:
        assert d["name"]
        assert len(d["id"].split(":")) == 6


def test_mock_deterministic_across_calls(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    assert handler({}) == handler({})


def test_connected_only_filter(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    devices = _assert_io_standard(handler({"connected_only": True}))
    assert devices  # mock 数据里至少有一台已连接设备
    assert all(d["connected"] for d in devices)


def test_none_and_empty_input(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    _assert_io_standard(handler(None))
    _assert_io_standard(handler({}))


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
