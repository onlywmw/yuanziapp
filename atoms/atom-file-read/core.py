# core.py
import base64
import os


def handler(data):
    """
    读取本地文件内容
    :param data: dict, 例如 {"path": "/tmp/example.txt", "mode": "text"}
    :return: dict, 包含 content/size 等
    """
    try:
        path = data.get("path")
        if not path:
            return {"status": "error", "message": "missing required field: path"}

        mode = data.get("mode", "text")  # text 或 base64
        max_size = int(data.get("max_size", 5 * 1024 * 1024))  # 默认限制 5MB

        if not os.path.isfile(path):
            return {"status": "error", "message": f"file not found: {path}"}

        size = os.path.getsize(path)
        if size > max_size:
            return {"status": "error", "message": f"file too large: {size} bytes > {max_size}"}

        if mode == "base64":
            with open(path, "rb") as f:
                content = base64.b64encode(f.read()).decode("utf-8")
        else:
            encoding = data.get("encoding", "utf-8")
            with open(path, "r", encoding=encoding, errors="replace") as f:
                content = f.read()

        return {
            "status": "success",
            "data": {
                "path": path,
                "size": size,
                "mode": mode,
                "content": content
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
