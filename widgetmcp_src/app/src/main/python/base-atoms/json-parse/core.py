# core.py — system.json-parse JSON 解析（基础原子，内置不可注册）
import json


def handler(data):
    """
    解析 JSON 文本
    :param data: {"text": "{\"key\": \"value\"}"}
    """
    try:
        text = data.get("text")
        if text is None:
            return {"status": "error", "message": "missing required field: text"}
        parsed = json.loads(str(text))
        return {"status": "success", "data": {"data": parsed}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
