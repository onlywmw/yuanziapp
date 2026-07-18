# core.py


def handler(data):
    """
    将字符串按分隔符拆分为列表
    :param data: dict, 例如 {"text": "a,b,c", "delimiter": ","}
    :return: dict, 例如 {"status": "success", "data": {"parts": ["a", "b", "c"]}}
    """
    try:
        text = str(data.get("text", ""))
        delimiter = str(data.get("delimiter", ","))
        maxsplit = data.get("maxsplit", -1)

        if maxsplit == -1:
            parts = text.split(delimiter)
        else:
            parts = text.split(delimiter, int(maxsplit))

        return {"status": "success", "data": {"parts": parts, "count": len(parts)}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
