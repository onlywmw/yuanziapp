"""system.ai 意图理解原子测试（base-atoms/ai/core.py）。

覆盖：六类意图正向用例、unknown 兜底、参数提取、输入校验、provider 回退。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ATOMS_DIR = Path(__file__).resolve().parents[1]


def _load():
    path = ATOMS_DIR / "ai" / "core.py"
    spec = importlib.util.spec_from_file_location("core_ai", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def core():
    module = _load()
    module._PROVIDERS.clear()  # 每个用例独立的 provider 缓存
    yield module
    module._PROVIDERS.clear()


def _run(core, query, **extra):
    payload = {"query": query}
    payload.update(extra)
    r = core.handler(payload)
    assert r["status"] == "success", r
    return r["data"]


# ---------- 六类意图正向用例 + 参数提取 ----------


def test_play_music_with_artist(core):
    d = _run(core, "我想听周杰伦的歌")
    assert d["intent"] == "play_music"
    assert d["params"]["artist"] == "周杰伦"
    assert d["source"] == "rules"
    assert 0.0 < d["confidence"] <= 1.0


def test_play_music_with_song_title(core):
    d = _run(core, "播放《晴天》")
    assert d["intent"] == "play_music"
    assert d["params"]["song"] == "晴天"


def test_weather_query_city(core):
    d = _run(core, "北京今天天气怎么样")
    assert d["intent"] == "weather_query"
    assert d["params"]["city"] == "北京"
    assert d["matched_atoms"] == ["system.http-get"]


def test_weather_query_time_words_not_city(core):
    d = _run(core, "今天天气怎么样")
    assert d["intent"] == "weather_query"
    assert "city" not in d["params"]  # 时间词不得误提取为城市


def test_note_diary_content(core):
    d = _run(core, "帮我记一下明天下午三点开会")
    assert d["intent"] == "note_diary"
    assert d["params"]["content"] == "明天下午三点开会"
    assert d["matched_atoms"] == ["system.file-write"]


def test_device_control_open(core):
    d = _run(core, "打开卧室的灯")
    assert d["intent"] == "device_control"
    assert d["params"] == {"action": "on", "device": "卧室的灯"}


def test_device_control_ba_pattern(core):
    d = _run(core, "把空调关了")
    assert d["intent"] == "device_control"
    assert d["params"] == {"device": "空调", "action": "off"}


def test_search_atom(core):
    d = _run(core, "搜索正则匹配原子")
    assert d["intent"] == "search_atom"
    assert d["params"]["keyword"] == "正则匹配"
    assert d["matched_atoms"] == ["system.string-match"]


def test_search_verb_without_atom_target_is_not_search_atom(core):
    d = _run(core, "搜索明天的机票")
    assert d["intent"] != "search_atom"


def test_time_query(core):
    d = _run(core, "现在几点了")
    assert d["intent"] == "time_query"
    assert d["params"]["field"] == "time"
    assert d["matched_atoms"] == ["system.date-time"]


# ---------- unknown 兜底 ----------


def test_unknown_fallback(core):
    d = _run(core, "叽里咕噜随便说说")
    assert d["intent"] == "unknown"
    assert d["confidence"] <= 0.2
    assert d["matched_atoms"] == []
    assert d["matched_workflows"] == []
    assert d["source"] == "rules"


# ---------- 输出契约 ----------


def test_output_contract(core):
    d = _run(core, "我想听适合下雨天的歌", context={"scene": "home"})
    assert set(d) == {
        "intent", "params", "matched_atoms",
        "matched_workflows", "confidence", "source",
    }
    assert isinstance(d["intent"], str)
    assert isinstance(d["params"], dict)
    assert isinstance(d["matched_atoms"], list)
    assert isinstance(d["matched_workflows"], list)
    assert 0.0 <= d["confidence"] <= 1.0
    assert d["source"] in ("rules", "onnx")


# ---------- 输入校验 ----------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": ""},
        {"query": "   "},
        {"query": 123},
        {"query": "听歌", "context": "not-a-dict"},
        "not a dict",
    ],
)
def test_invalid_input(core, payload):
    r = core.handler(payload)
    assert r["status"] == "error"
    assert r["message"]


# ---------- provider 回退逻辑 ----------


def test_default_provider_is_rules(core, monkeypatch):
    monkeypatch.delenv("AI_MODEL_PATH", raising=False)
    assert isinstance(core.get_provider(), core.RulesProvider)


def test_onnx_fallback_when_runtime_missing(core, monkeypatch, tmp_path):
    """模拟 onnxruntime 不存在：即使模型文件存在也静默回退规则。"""
    model = tmp_path / "intent.onnx"
    model.write_bytes(b"fake-onnx")
    monkeypatch.setenv("AI_MODEL_PATH", str(model))
    monkeypatch.setitem(sys.modules, "onnxruntime", None)  # import 即 ImportError

    assert isinstance(core.get_provider(), core.RulesProvider)
    d = _run(core, "现在几点了")
    assert d["intent"] == "time_query"
    assert d["source"] == "rules"


def test_onnx_fallback_when_model_load_fails(core, monkeypatch, tmp_path):
    """onnxruntime 可导入但模型加载失败：回退规则。"""
    import types

    fake = types.SimpleNamespace(
        InferenceSession=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad model"))
    )
    model = tmp_path / "broken.onnx"
    model.write_bytes(b"not-a-model")
    monkeypatch.setenv("AI_MODEL_PATH", str(model))
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)

    assert isinstance(core.get_provider(), core.RulesProvider)
    d = _run(core, "现在几点了")
    assert d["source"] == "rules"


def test_onnx_not_implemented_falls_back_to_rules(core, monkeypatch, tmp_path):
    """推理接口预留未实现（NotImplementedError）：handler 回退规则。"""
    import types

    fake = types.SimpleNamespace(InferenceSession=lambda *a, **k: object())
    model = tmp_path / "intent.onnx"
    model.write_bytes(b"fake-onnx")
    monkeypatch.setenv("AI_MODEL_PATH", str(model))
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)

    assert isinstance(core.get_provider(), core.OnnxProvider)
    d = _run(core, "现在几点了")
    assert d["intent"] == "time_query"
    assert d["source"] == "rules"
