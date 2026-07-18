# core.py — system.file-write 文件写入（基础原子，内置不可注册）
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
    写入本地文件（仅限白名单根目录内，content max 5MB）
    :param data: {"path": "...", "content": "...", "mode": "text"|"base64", "append": false, "encoding": "utf-8"}
    """
    try:
        path = data.get("path")
        content = data.get("content")
        if not path:
            return {"status": "error", "message": "missing required field: path"}
        if content is None:
            return {"status": "error", "message": "missing required field: content"}
        if not _is_allowed(path):
            return {
                "status": "error",
                "message": "path outside allowed roots (set ATOM_FILE_ROOTS)",
            }

        mode = data.get("mode", "text")
        append = bool(data.get("append", False))
        max_size = int(data.get("max_size", 5 * 1024 * 1024))

        if mode == "base64":
            raw = base64.b64decode(content)
        else:
            raw = content.encode(data.get("encoding", "utf-8"))
        if len(raw) > max_size:
            return {
                "status": "error",
                "message": f"content too large: {len(raw)} bytes > {max_size}",
            }

        parent = os.path.dirname(os.path.realpath(path))
        os.makedirs(parent, exist_ok=True)
        flag = "ab" if append else "wb"
        with open(path, flag) as f:
            written = f.write(raw)

        return {"status": "success", "data": {"path": path, "written": written}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
