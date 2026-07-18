# core.py — system.string-split 字符串拆分（基础原子，内置不可注册）


def handler(data):
    """
    拆分字符串
    :param data: {"text": "a,b,c", "delimiter": ",", "maxsplit": -1}
    """
    try:
        text = data.get("text")
        if text is None:
            return {"status": "error", "message": "missing required field: text"}
        delimiter = data.get("delimiter", ",")
        if not delimiter:
            return {"status": "error", "message": "delimiter must not be empty"}
        maxsplit = int(data.get("maxsplit", -1))
        parts = str(text).split(delimiter, maxsplit)
        return {"status": "success", "data": {"parts": parts, "count": len(parts)}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
