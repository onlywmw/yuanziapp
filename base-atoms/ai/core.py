# core.py — system.ai 本地意图理解（基础原子，内置不可注册）
"""
自然语言 → 结构化意图（intent/params/matched_atoms/matched_workflows）。

双轨实现（规则兜底为默认，ONNX 为可选增强，永远本地推理、不上云）：
- RulesProvider：中文关键词 + 正则参数提取，纯标准库、零依赖、<1ms。
- OnnxProvider：AI_MODEL_PATH 指向存在的本地模型且 onnxruntime 可导入时启用。
  选型 BAAI/bge-small-zh-v1.5（512 维句嵌入）+ prototypes.json 原型库余弦
  相似度；规则快路径优先，规则 miss 时才走模型补语义泛化，参数提取沿用规则
  正则。缺库 / 模型缺失 / 加载失败 / 推理异常时静默回退规则，输出 source 记
  'rules'。相似度阈值取环境变量 AI_ONNX_THRESHOLD，默认 0.55。
"""
import importlib.util
import json
import math
import os
import re

SOURCE_RULES = "rules"
SOURCE_ONNX = "onnx"

# 意图 → 现有 13 个基础原子的映射；无对应基础原子的意图置空列表
INTENT_ATOMS = {
    "play_music": [],  # 音乐播放原子尚未实现（感知层缺口）
    "weather_query": ["system.http-get"],  # 天气数据经公网 HTTP 获取
    "note_diary": ["system.file-write"],
    "device_control": [],  # 设备控制原子尚未实现（感知层缺口）
    "search_atom": ["system.string-match"],
    "time_query": ["system.date-time"],
}

# 城市提取时需剔除的时间/语气词（防止 "北京今天天气" 误提取为 "北京今天"）
_TIME_WORDS = (
    "今天", "明天", "后天", "昨天", "现在", "最近",
    "这周", "本周", "这几天", "这两天", "一下",
)

# 设备动作词 → 归一化动作
_DEVICE_ACTIONS = {
    "打开": "on", "开启": "on", "开了": "on",
    "关闭": "off", "关掉": "off", "关了": "off",
    "调高": "up", "调大": "up",
    "调低": "down", "调小": "down",
}


def _result(intent, params, confidence, source):
    """按三方定稿的输出契约组装结果，confidence 截断到 [0, 1]。"""
    return {
        "intent": intent,
        "params": params,
        "matched_atoms": list(INTENT_ATOMS.get(intent, [])),
        # 仓库暂无已注册工作流可静态映射，固定空列表，待工作流注册后补充
        "matched_workflows": [],
        "confidence": max(0.0, min(1.0, round(confidence, 2))),
        "source": source,
    }


def _extract_city(query):
    """从 "北京今天天气怎么样" 一类问句中提取城市名。"""
    m = re.search(r"([一-龥]{2,10}?)的?(?:天气|气温|温度)", query)
    if not m:
        return None
    city = m.group(1)
    for w in _TIME_WORDS:
        city = city.replace(w, "")
    city = city.strip("的")
    return city if len(city) >= 2 else None


class RulesProvider:
    """默认实现：中文意图模式库（关键词触发 + 正则提取参数），纯本地。"""

    source = SOURCE_RULES

    # 按优先级排列，先命中先返回；keyword 为子串匹配
    _RULES = (
        ("play_music", ("播放", "放歌", "想听", "听歌", "音乐", "来一首", "来首歌", "点歌")),
        ("note_diary", ("记一下", "记下", "记录", "备忘", "便签", "笔记", "日记")),
        ("device_control", ("打开", "开启", "关闭", "关掉", "调高", "调低", "调大", "调小",
                          "开灯", "关灯", "蓝牙", "WiFi", "wifi", "音量", "亮度", "空调")),
        ("search_atom", ("搜索", "查找", "搜一下", "搜一搜", "找一下")),
        ("weather_query", ("天气", "气温", "温度", "下雨", "下雪")),
        ("time_query", ("几点", "几号", "星期", "时间", "日期")),
    )

    def predict(self, query, context):
        for intent, keywords in self._RULES:
            if not any(k in query for k in keywords):
                continue
            # search_atom 需同时出现搜索动词与原子/工作流类目标词，
            # 避免 "搜索明天的机票" 误判为找原子
            if intent == "search_atom" and not any(
                t in query for t in ("原子", "工作流", "功能", "能力", "atom", "workflow")
            ):
                continue
            params = self._extract(intent, query)
            confidence = min(0.95, 0.8 + 0.05 * len(params))
            return _result(intent, params, confidence, self.source)
        # 无任何规则命中：低置信度兜底
        return _result("unknown", {}, 0.1, self.source)

    def _extract(self, intent, query):
        """按意图做正则参数提取；提取失败不影响主流程，返回已得参数。"""
        try:
            if intent == "play_music":
                return self._extract_music(query)
            if intent == "weather_query":
                city = _extract_city(query)
                return {"city": city} if city else {}
            if intent == "note_diary":
                return self._extract_note(query)
            if intent == "device_control":
                return self._extract_device(query)
            if intent == "search_atom":
                return self._extract_search(query)
            if intent == "time_query":
                return self._extract_time(query)
        except Exception:
            pass
        return {}

    @staticmethod
    def _extract_music(query):
        params = {}
        m = re.search(r"《([^》]{1,50})》", query)
        if m:
            params["song"] = m.group(1)
        m = re.search(r"听([一-龥A-Za-z0-9·]{1,15}?)的歌", query)
        if m:
            params["artist"] = m.group(1)
        if "下雨" in query or "雨天" in query:
            params["scene"] = "rainy_day"
        return params

    @staticmethod
    def _extract_note(query):
        m = re.search(
            r"(?:记一下|记下|记录|写个备忘|记个备忘|备忘|写个便签|记个笔记|写个笔记)"
            r"[：:，,]?\s*(.{1,200})$",
            query,
        )
        return {"content": m.group(1).strip()} if m else {}

    @staticmethod
    def _extract_device(query):
        m = re.search(
            r"(打开|开启|关闭|关掉|调高|调低|调大|调小)([一-龥A-Za-z0-9]{1,12}?)(?:一下)?$",
            query,
        )
        if not m:
            m = re.search(
                r"把([一-龥A-Za-z0-9]{1,12}?)(?:给)?(打开|开启|关闭|关掉|关了|开了)",
                query,
            )
            if m:
                return {"device": m.group(1), "action": _DEVICE_ACTIONS[m.group(2)]}
            return {}
        return {"action": _DEVICE_ACTIONS[m.group(1)], "device": m.group(2)}

    @staticmethod
    def _extract_search(query):
        m = re.search(r"(?:搜索|查找|搜一下|搜一搜|找一下)[：:]?\s*(.{1,50})$", query)
        if not m:
            return {}
        keyword = re.sub(r"(的)?(原子|工作流|功能|能力)$", "", m.group(1).strip())
        params = {"keyword": keyword}
        if "工作流" in query or "workflow" in query:
            params["target"] = "workflow"
        else:
            params["target"] = "atom"
        return params

    @staticmethod
    def _extract_time(query):
        if "星期" in query:
            return {"field": "weekday"}
        if "几号" in query or "日期" in query:
            return {"field": "date"}
        return {"field": "time"}


class OnnxProvider:
    """可选增强：本地 ONNX 语义意图识别（Phase 2 实现）。

    bge-small-zh-v1.5 句嵌入 + 原型库相似度：
    - 规则快路径优先：规则命中直接返回规则结果（source 记 'rules'）；
    - 规则 miss 时编码 query 与原型例句（[CLS] 池化 + L2 归一化，bge 官方
      做法），余弦相似度取最高分意图，source 记 'onnx'；
    - 阈值 AI_ONNX_THRESHOLD（默认 0.55）以下判 unknown 低置信；
    - 参数提取沿用规则正则；原型向量首次使用时惰性编码并缓存；
    - 任何加载 / 推理异常都抛给 handler，静默回退规则兜底。
    """

    source = SOURCE_ONNX

    def __init__(self, model_path):
        import onnxruntime  # 缺库时 ImportError → 上层回退规则

        self._session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self._model_path = str(model_path)
        self._tokenizer = None  # 惰性加载（vocab.txt 与模型同目录）
        self._prototypes = None  # 惰性编码缓存：intent → [单位向量, ...]
        self._rules = RulesProvider()  # 快路径 + 参数提取复用

    def predict(self, query, context):
        # 快路径：规则命中直接用规则（<1ms，不碰模型）
        rules_result = self._rules.predict(query, context)
        if rules_result["intent"] != "unknown":
            return rules_result
        # 慢路径：ONNX 原型相似度补语义泛化
        self._ensure_ready()
        vec = self._encode(query)
        intent, score = self._best_match(vec)
        threshold = _onnx_threshold()
        if intent is None or score < threshold:
            # unknown 低置信：按相对阈值的接近程度缩放到 [0, 0.2]，
            # 与规则 unknown（0.1）保持同一低置信语义
            confidence = 0.2 * max(0.0, score) / max(threshold, 1e-6)
            return _result("unknown", {}, confidence, self.source)
        params = self._rules._extract(intent, query)
        return _result(intent, params, score, self.source)

    def _ensure_ready(self):
        """首次 ONNX 推理前加载分词器并编码原型库；失败抛异常由 handler 回退。"""
        if self._tokenizer is None:
            vocab_path = os.path.join(os.path.dirname(self._model_path), "vocab.txt")
            self._tokenizer = _load_tokenizer_class()(vocab_path)
        if self._prototypes is None:
            proto_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "prototypes.json"
            )
            with open(proto_path, encoding="utf-8") as f:
                raw = json.load(f)
            self._prototypes = {
                intent: [self._encode(s) for s in examples]
                for intent, examples in raw.items()
            }

    def _encode(self, text):
        """文本 → [CLS] 池化 + L2 归一化的 512 维单位向量（bge 官方做法）。"""
        inputs = self._tokenizer.encode(text)
        feed = {name: _as_int_array(value) for name, value in inputs.items()}
        outputs = self._session.run(None, feed)
        cls_vec = outputs[0][0][0]  # last_hidden_state 的 [CLS] 位置
        if hasattr(cls_vec, "tolist"):  # 兼容 numpy 输出与测试 mock 的嵌套列表
            cls_vec = cls_vec.tolist()
        return _l2_normalize([float(x) for x in cls_vec])

    def _best_match(self, vec):
        """与全部原型向量取余弦（双方已归一化 → 点积），返回 (意图, 最高分)。"""
        best_intent, best_score = None, -1.0
        for intent, protos in self._prototypes.items():
            for proto in protos:
                score = sum(a * b for a, b in zip(vec, proto))
                if score > best_score:
                    best_intent, best_score = intent, score
        return best_intent, best_score


def _onnx_threshold():
    """相似度阈值：环境变量 AI_ONNX_THRESHOLD 可调，非法值回退默认 0.55。"""
    try:
        return float(os.environ.get("AI_ONNX_THRESHOLD", "0.55"))
    except ValueError:
        return 0.55


def _l2_normalize(vec):
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _as_int_array(rows):
    """onnxruntime 需要 int64 numpy 输入；无 numpy（如测试 mock）退化为嵌套列表。"""
    try:
        import numpy as np
    except ImportError:
        return rows
    return np.asarray(rows, dtype=np.int64)


def _load_tokenizer_class():
    """按文件路径加载同目录 tokenizer.py（core.py 常以非包方式被 importlib 载入）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokenizer.py")
    spec = importlib.util.spec_from_file_location("ai_wordpiece_tokenizer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.WordPieceTokenizer


_RULES_PROVIDER = RulesProvider()
_PROVIDERS = {}  # model_path → OnnxProvider 缓存，避免重复加载模型


def get_provider():
    """集中选择 provider：ONNX 可用则用，否则规则兜底（默认）。"""
    model_path = os.environ.get("AI_MODEL_PATH", "")
    if model_path and os.path.isfile(model_path):
        if model_path in _PROVIDERS:
            return _PROVIDERS[model_path]
        try:
            provider = OnnxProvider(model_path)
            _PROVIDERS[model_path] = provider
            return provider
        except Exception:
            pass  # 缺库 / 模型加载失败：静默回退规则
    return _RULES_PROVIDER


def handler(data):
    """
    本地意图理解
    :param data: {"query": "我想听周杰伦的歌", "context": {...}（可选）}
    :return: {"status": "success", "data": {"intent": str, "params": object,
             "matched_atoms": list, "matched_workflows": list,
             "confidence": 0~1, "source": "rules"|"onnx"}}
    """
    try:
        if not isinstance(data, dict):
            return {"status": "error", "message": "payload must be a JSON object"}
        query = data.get("query")
        if not isinstance(query, str) or not query.strip():
            return {"status": "error", "message": "missing required field: query"}
        context = data.get("context")
        if context is not None and not isinstance(context, dict):
            return {"status": "error", "message": "context must be an object"}

        query = query.strip()
        provider = get_provider()
        try:
            result = provider.predict(query, context or {})
        except Exception:
            # ONNX 推理 / 词表 / 原型库任何失败：静默回退规则兜底
            result = _RULES_PROVIDER.predict(query, context or {})
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
