"""system.ai Phase 2 测试（base-atoms/ai/ 的 ONNX 语义意图识别）。

覆盖：WordPiece 分词器（小词表 fixture）、OnnxProvider 匹配/阈值/规则快路径/
静默回退（mock InferenceSession）、原型库完整性、真实模型集成（skipUnless 守卫）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

ATOMS_DIR = Path(__file__).resolve().parents[1]
AI_DIR = ATOMS_DIR / "ai"

# 小词表 fixture：行号即 token id，覆盖分词器各分支所需最小集合
_VOCAB = "\n".join(
    [
        "[PAD]",  # 0
        "[UNK]",  # 1
        "[CLS]",  # 2
        "[SEP]",  # 3
        "，",  # 4
        "。",  # 5
        "我",  # 6
        "想",  # 7
        "听",  # 8
        "歌",  # 9
        "音",  # 10
        "乐",  # 11
        "播",  # 12
        "放",  # 13
        "ab",  # 14
        "##s",  # 15
        "##cd",  # 16
        "abc",  # 17
    ]
)


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def core():
    module = _load_module("core_ai_onnx_test", AI_DIR / "core.py")
    module._PROVIDERS.clear()  # 每个用例独立的 provider 缓存
    yield module
    module._PROVIDERS.clear()


@pytest.fixture()
def tokenizer_mod():
    return _load_module("ai_tokenizer_test", AI_DIR / "tokenizer.py")


@pytest.fixture()
def vocab_file(tmp_path):
    path = tmp_path / "vocab.txt"
    path.write_text(_VOCAB, encoding="utf-8")
    return path


class _FakeSession:
    """脚本化 last_hidden_state 的假 InferenceSession，并记录 feed 便于断言。"""

    def __init__(self, hidden):
        self._hidden = hidden
        self.feeds = []

    def run(self, output_names, feed):
        self.feeds.append(feed)
        return [self._hidden]


def _make_provider(core, monkeypatch, tmp_path, session):
    """用假 onnxruntime 构造 OnnxProvider（模型文件为占位字节）。"""
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake-onnx")
    fake = types.SimpleNamespace(InferenceSession=lambda *a, **k: session)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    return core.OnnxProvider(str(model))


# ---------- WordPiece 分词器 ----------


def test_tokenizer_chinese_char_split(tokenizer_mod, vocab_file):
    tok = tokenizer_mod.WordPieceTokenizer(str(vocab_file))
    assert tok.tokenize("我想听歌") == ["我", "想", "听", "歌"]


def test_tokenizer_punctuation_split(tokenizer_mod, vocab_file):
    tok = tokenizer_mod.WordPieceTokenizer(str(vocab_file))
    assert tok.tokenize("听歌，") == ["听", "歌", "，"]


def test_tokenizer_wordpiece_continuation(tokenizer_mod, vocab_file):
    tok = tokenizer_mod.WordPieceTokenizer(str(vocab_file))
    assert tok.tokenize("abs") == ["ab", "##s"]
    # "abc" 贪心命中后 "##d" 无匹配 → 整个词判 [UNK]（bert 官方行为）
    assert tok.tokenize("abcd") == ["[UNK]"]


def test_tokenizer_lowercase(tokenizer_mod, vocab_file):
    tok = tokenizer_mod.WordPieceTokenizer(str(vocab_file))
    assert tok.tokenize("AbC") == ["abc"]


def test_tokenizer_unk_fallback(tokenizer_mod, vocab_file):
    tok = tokenizer_mod.WordPieceTokenizer(str(vocab_file))
    assert tok.tokenize("xyz") == ["[UNK]"]
    assert tok.tokenize("听歌xyz") == ["听", "歌", "[UNK]"]


def test_tokenizer_encode_special_tokens(tokenizer_mod, vocab_file):
    tok = tokenizer_mod.WordPieceTokenizer(str(vocab_file))
    encoded = tok.encode("我想听歌")
    ids = encoded["input_ids"][0]
    assert ids == [2, 6, 7, 8, 9, 3]  # [CLS] 我想听歌 [SEP]
    assert encoded["attention_mask"] == [[1] * len(ids)]
    assert encoded["token_type_ids"] == [[0] * len(ids)]


def test_tokenizer_truncation(tokenizer_mod, vocab_file):
    tok = tokenizer_mod.WordPieceTokenizer(str(vocab_file), max_len=6)
    ids = tok.encode("我想听歌播放音乐xyz")[  # 超长的词判 [UNK] 也照常占长度
        "input_ids"
    ][0]
    assert len(ids) == 6
    assert ids[0] == 2 and ids[-1] == 3  # 截断后仍以 [SEP] 收尾


def test_tokenizer_vocab_missing_unk(tokenizer_mod, tmp_path):
    bad = tmp_path / "vocab.txt"
    bad.write_text("[PAD]\n[CLS]\n[SEP]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="\[UNK\]"):
        tokenizer_mod.WordPieceTokenizer(str(bad))


# ---------- OnnxProvider：编码 / 匹配 / 阈值 ----------


def test_encode_cls_pooling_and_l2_norm(core, monkeypatch, tmp_path, tokenizer_mod, vocab_file):
    """[CLS] 池化 + L2 归一化：[3,4] → [0.6,0.8]，且 feed 键齐全。"""
    session = _FakeSession([[[3.0, 4.0], [9.9, 9.9]]])  # [1, 2token, 2维]
    provider = _make_provider(core, monkeypatch, tmp_path, session)
    provider._tokenizer = tokenizer_mod.WordPieceTokenizer(str(vocab_file))

    vec = provider._encode("我想听歌")
    assert vec == pytest.approx([0.6, 0.8])
    assert set(session.feeds[0]) == {"input_ids", "attention_mask", "token_type_ids"}


def test_onnx_match_best_intent(core, monkeypatch, tmp_path):
    """规则 miss 时取相似度最高的意图，source 记 'onnx'。"""
    provider = _make_provider(core, monkeypatch, tmp_path, _FakeSession([[[1.0, 0.0]]]))
    provider._tokenizer = object()  # 跳过词表加载
    provider._prototypes = {"play_music": [[1.0, 0.0]], "weather_query": [[0.0, 1.0]]}
    monkeypatch.setattr(provider, "_encode", lambda text: [1.0, 0.0])

    r = provider.predict("来点治愈的旋律", {})
    assert r["intent"] == "play_music"
    assert r["source"] == "onnx"
    assert r["confidence"] == 1.0
    assert r["matched_workflows"] == []


def test_onnx_params_extracted_by_rules_regex(core, monkeypatch, tmp_path):
    """ONNX 定意图后，参数提取沿用规则正则（书名号歌名）。"""
    provider = _make_provider(core, monkeypatch, tmp_path, _FakeSession([[[1.0, 0.0]]]))
    provider._tokenizer = object()
    provider._prototypes = {"play_music": [[1.0, 0.0]]}
    monkeypatch.setattr(provider, "_encode", lambda text: [1.0, 0.0])

    r = provider.predict("来首《晴天》暖暖心", {})  # "来首" 非规则关键词 → 规则 miss
    assert r["intent"] == "play_music"
    assert r["source"] == "onnx"
    assert r["params"]["song"] == "晴天"


def test_onnx_below_threshold_is_unknown(core, monkeypatch, tmp_path):
    """相似度低于默认阈值 0.55 → unknown 低置信。"""
    provider = _make_provider(core, monkeypatch, tmp_path, _FakeSession([[[0.5, 0.5]]]))
    provider._tokenizer = object()
    provider._prototypes = {"play_music": [[1.0, 0.0]], "weather_query": [[0.0, 1.0]]}
    monkeypatch.setattr(provider, "_encode", lambda text: [0.5, 0.5])  # 最高 0.5 < 0.55

    r = provider.predict("来点治愈的旋律", {})
    assert r["intent"] == "unknown"
    assert r["source"] == "onnx"
    assert r["confidence"] == 0.18  # 0.2 * 0.5/0.55 缩放进低置信区间
    assert r["matched_atoms"] == []


def test_onnx_threshold_env_adjustable(core, monkeypatch, tmp_path):
    """AI_ONNX_THRESHOLD 可调低阈值使 0.5 也能命中。"""
    monkeypatch.setenv("AI_ONNX_THRESHOLD", "0.49")
    provider = _make_provider(core, monkeypatch, tmp_path, _FakeSession([[[0.5, 0.5]]]))
    provider._tokenizer = object()
    provider._prototypes = {"play_music": [[1.0, 0.0]], "weather_query": [[0.0, 1.0]]}
    monkeypatch.setattr(provider, "_encode", lambda text: [0.5, 0.5])

    r = provider.predict("来点治愈的旋律", {})
    assert r["intent"] == "play_music"
    assert r["source"] == "onnx"
    assert r["confidence"] == 0.5


def test_rules_fast_path_takes_priority(core, monkeypatch, tmp_path):
    """规则命中时直接走规则快路径，不触碰模型推理。"""
    provider = _make_provider(core, monkeypatch, tmp_path, _FakeSession([[[1.0, 0.0]]]))

    def _boom(text):
        raise AssertionError("规则快路径下不应调用模型编码")

    monkeypatch.setattr(provider, "_encode", _boom)
    r = provider.predict("现在几点了", {})
    assert r["intent"] == "time_query"
    assert r["source"] == "rules"


# ---------- handler 端到端：ONNX 路径与静默回退 ----------


def test_handler_onnx_path_when_rules_miss(core, monkeypatch, tmp_path, vocab_file):
    """词表齐全 + 模型可用：规则 miss 的 query 走 ONNX，source 记 'onnx'。"""
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake-onnx")
    # vocab_file 已在 tmp_path，与模型同目录
    fake = types.SimpleNamespace(
        InferenceSession=lambda *a, **k: _FakeSession([[[1.0, 0.0]]])
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    monkeypatch.setenv("AI_MODEL_PATH", str(model))

    r = core.handler({"query": "来点治愈的旋律"})
    assert r["status"] == "success"
    d = r["data"]
    assert d["source"] == "onnx"
    assert d["intent"] == "play_music"  # 全部原型同向量时取遍历首个意图
    assert d["confidence"] == 1.0


def test_handler_fallback_when_vocab_missing(core, monkeypatch, tmp_path):
    """模型存在但词表缺失：静默回退规则，query 规则 miss → unknown/rules。"""
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake-onnx")  # 同目录故意不放 vocab.txt
    fake = types.SimpleNamespace(
        InferenceSession=lambda *a, **k: _FakeSession([[[1.0, 0.0]]])
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    monkeypatch.setenv("AI_MODEL_PATH", str(model))

    r = core.handler({"query": "来点治愈的旋律"})
    assert r["status"] == "success"
    d = r["data"]
    assert d["source"] == "rules"
    assert d["intent"] == "unknown"


def test_handler_fallback_when_inference_raises(core, monkeypatch, tmp_path, vocab_file):
    """推理抛异常：静默回退规则，不暴露错误给调用方。"""

    class _BoomSession:
        def run(self, *a, **k):
            raise RuntimeError("inference boom")

    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake-onnx")
    fake = types.SimpleNamespace(InferenceSession=lambda *a, **k: _BoomSession())
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    monkeypatch.setenv("AI_MODEL_PATH", str(model))

    r = core.handler({"query": "来点治愈的旋律"})
    assert r["status"] == "success"
    assert r["data"]["source"] == "rules"
    assert r["data"]["intent"] == "unknown"


# ---------- 原型库完整性 ----------


def test_prototypes_library_integrity():
    data = json.loads((AI_DIR / "prototypes.json").read_text(encoding="utf-8"))
    assert set(data) == {
        "play_music",
        "weather_query",
        "note_diary",
        "device_control",
        "search_atom",
        "time_query",
    }
    for intent, examples in data.items():
        assert 6 <= len(examples) <= 10, intent
        assert all(isinstance(s, str) and s.strip() for s in examples)
        assert len(set(examples)) == len(examples), f"{intent} 存在重复例句"


def test_prototypes_cover_rules_blind_spots(core):
    """每意图至少 3 条例句是规则覆盖不到的表达（语义泛化的价值所在）。"""
    data = json.loads((AI_DIR / "prototypes.json").read_text(encoding="utf-8"))
    rules = core.RulesProvider()
    for intent, examples in data.items():
        blind = [s for s in examples if rules.predict(s, {})["intent"] == "unknown"]
        assert len(blind) >= 3, f"{intent} 规则盲区例句不足：{blind}"


# ---------- 真实模型集成（模型存在才跑） ----------

_REAL_MODEL = os.environ.get("AI_MODEL_PATH", "")
_REAL_READY = (
    bool(_REAL_MODEL)
    and os.path.isfile(_REAL_MODEL)
    and os.path.isfile(os.path.join(os.path.dirname(_REAL_MODEL), "vocab.txt"))
)


@pytest.mark.skipif(
    not _REAL_READY, reason="AI_MODEL_PATH 未指向真实模型（含同目录 vocab.txt），跳过集成测试"
)
def test_real_model_semantic_generalization(core):
    """真实 bge-small-zh：规则覆盖不到的 '来首 emo 的歌' 应判 play_music。"""
    pytest.importorskip("onnxruntime")
    provider = core.OnnxProvider(_REAL_MODEL)
    r = provider.predict("来首 emo 的歌", {})
    assert r["intent"] == "play_music"
    assert r["source"] == "onnx"
    assert r["confidence"] >= 0.55
