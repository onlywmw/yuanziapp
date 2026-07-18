# core.py
import requests


def handler(data):
    """
    发起 HTTP GET 请求
    :param data: dict, 例如 {"url": "https://api.example.com/data", "headers": {"Accept": "application/json"}, "timeout": 30}
    :return: dict, 包含 status_code/headers/body/text
    """
    try:
        url = data.get("url")
        if not url:
            return {"status": "error", "message": "missing required field: url"}

        headers = data.get("headers") or {}
        timeout = int(data.get("timeout", 30))
        allow_redirects = data.get("allow_redirects", True)

        resp = requests.get(
            url, headers=headers, timeout=timeout, allow_redirects=allow_redirects
        )

        # 尽量返回文本，但限制长度避免过大
        text = resp.text
        max_len = int(data.get("max_length", 100000))
        if len(text) > max_len:
            text = text[:max_len]

        return {
            "status": "success",
            "data": {
                "status_code": resp.status_code,
                "url": resp.url,
                "headers": dict(resp.headers),
                "text": text,
                "encoding": resp.encoding,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
