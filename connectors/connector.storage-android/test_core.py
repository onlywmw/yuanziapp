# test_core.py — connector.storage-android 单元测试（hermetic）
#
# 全部测试在 mock 模式（YUANZI_CONNECTOR_MOCK=1，monkeypatch 注入）下运行，
# 验证输出符合 storage I/O 接口标准（schema.storage-v1）：
#   {"files": [{"name": str, "path": str, "size": number}, ...]}
# 不触碰真实 Android 环境、不访问网络、不依赖外部状态。

import core
from core import handler

# schema.storage-v1 输出契约：files 数组元素的全部键与类型
FILE_KEYS = {"name", "path", "size"}


def _assert_io_standard(result):
    """校验 handler 输出严格符合 storage I/O 标准。"""
    assert result["status"] == "success"
    files = result["data"]["files"]
    assert isinstance(files, list)
    for f in files:
        assert set(f.keys()) == FILE_KEYS
        assert isinstance(f["name"], str)
        assert isinstance(f["path"], str)
        assert isinstance(f["size"], (int, float))
    return files


def test_mock_returns_success(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    result = handler({})
    assert result["status"] == "success"
    assert "data" in result


def test_mock_output_matches_io_standard(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    files = _assert_io_standard(handler({}))
    # mock 数据为一小批假文件条目
    assert len(files) >= 2


def test_mock_data_is_realistic(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    files = _assert_io_standard(handler({}))
    # 逼真性：path 形如 content URI 或可重新打开的文件引用，大小为正
    for f in files:
        assert f["name"]
        assert f["path"].startswith(("content://", "/"))
        assert f["size"] > 0
    assert any(f["path"].startswith("content://") for f in files)


def test_mock_deterministic_across_calls(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    assert handler({}) == handler({})


def test_limit_param(monkeypatch):
    """limit 入参截断 mock 列表；非法值回退默认。"""
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    files = _assert_io_standard(handler({"limit": 2}))
    assert len(files) == 2
    files = _assert_io_standard(handler({"limit": "not-a-number"}))
    assert len(files) >= 2


def test_none_and_empty_input(monkeypatch):
    monkeypatch.setenv("YUANZI_CONNECTOR_MOCK", "1")
    _assert_io_standard(handler(None))
    _assert_io_standard(handler({}))


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
    """桌面环境无 Chaquopy java 桥接时模块可导入不崩。"""
    assert hasattr(core, "handler")
