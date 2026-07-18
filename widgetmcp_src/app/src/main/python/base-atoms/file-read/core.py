# core.py — system.file-read 文件读取（基础原子，内置不可注册）
import base64
import os


def _allowed_roots():
    raw = os.environ.get("ATOM_FILE_ROOTS", "")
    if raw.strip():
        return [os.path.realpath(p) for p in raw.split(os.pathsep) if p.strip()]
    return [os.path.realpath(os.getcwd())]


def _is_allowed(path):
    real = os.path.realpath(path)
    for root in _allowed_roots():
        try:
            if os.path.commonpath([real, root]) == root:
                return True
        except ValueError:
            continue
    return False


def handler(data):
    """
    读取本地文件内容（仅限白名单根目录内，max 5MB）
    :param data: {"path": "...", "mode": "text"|"base64", "encoding": "utf-8", "max_size": 5242880}
    """
    try:
        path = data.get("path")
        if not path:
            return {"status": "error", "message": "missing required field: path"}
        if not _is_allowed(path):
            return {
                "status": "error",
                "message": "path outside allowed roots (set ATOM_FILE_ROOTS)",
            }

        mode = data.get("mode", "text")
        max_size = int(data.get("max_size", 5 * 1024 * 1024))

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
