# core.py — system.string-match 正则匹配（基础原子，内置不可注册）
import re

_FLAG_MAP = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL, "x": re.VERBOSE}
_MAX_MATCHES = 10_000


def handler(data):
    r"""
    正则匹配
    :param data: {"text": "hello world", "pattern": "\w+", "flags": "imsx"}
    """
    try:
        text = data.get("text")
        pattern = data.get("pattern")
        if text is None or not pattern:
            return {
                "status": "error",
                "message": "missing required field: text/pattern",
            }

        flags = 0
        for ch in data.get("flags", ""):
            if ch in _FLAG_MAP:
                flags |= _FLAG_MAP[ch]

        matches = re.findall(pattern, str(text), flags)
        # findall 在含分组时返回元组，统一展平为字符串
        flat = [
            " ".join(m) if isinstance(m, tuple) else m for m in matches[:_MAX_MATCHES]
        ]
        return {"status": "success", "data": {"matches": flat, "count": len(flat)}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
