# core.py
import base64
import os


def _allowed_roots():
    """允许读取的根目录白名单。

    通过环境变量 ATOM_FILE_READ_ROOTS 配置（os.pathsep 分隔多个根目录）。
    缺省只允许当前工作目录及其子目录（BUG-007 沙箱）。
    """
    raw = os.environ.get("ATOM_FILE_READ_ROOTS", "")
    if raw.strip():
        return [os.path.realpath(p) for p in raw.split(os.pathsep) if p.strip()]
    return [os.path.realpath(os.getcwd())]


def _is_allowed(path):
    """realpath 归一化后做前缀检查，拒绝 .. 穿越与沙箱外路径。"""
    real = os.path.realpath(path)
    for root in _allowed_roots():
        try:
            if os.path.commonpath([real, root]) == root:
                return True
        except ValueError:
            continue  # Windows 上不同盘符会抛 ValueError
    return False


def handler(data):
    """
    读取本地文件内容（仅限白名单根目录内）
    :param data: dict, 例如 {"path": "/tmp/example.txt", "mode": "text"}
    :return: dict, 包含 content/size 等
    """
    try:
        path = data.get("path")
        if not path:
            return {"status": "error", "message": "missing required field: path"}

        if not _is_allowed(path):
            return {
                "status": "error",
                "message": "path outside allowed roots (set ATOM_FILE_READ_ROOTS)",
            }

        mode = data.get("mode", "text")  # text 或 base64
        max_size = int(data.get("max_size", 5 * 1024 * 1024))  # 默认限制 5MB

        if not os.path.isfile(path):
            return {"status": "error", "message": f"file not found: {path}"}

        size = os.path.getsize(path)
        if size > max_size:
            return {
                "status": "error",
                "message": f"file too large: {size} bytes > {max_size}",
            }

        if mode == "base64":
            with open(path, "rb") as f:
                content = base64.b64encode(f.read()).decode("utf-8")
        else:
            encoding = data.get("encoding", "utf-8")
            with open(path, "r", encoding=encoding, errors="replace") as f:
                content = f.read()

        return {
            "status": "success",
            "data": {"path": path, "size": size, "mode": mode, "content": content},
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
