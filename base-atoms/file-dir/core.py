# core.py — system.file-dir 文件夹操作（基础原子，内置不可注册）
import os

_MAX_ENTRIES = 10_000


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
    文件夹操作
    :param data: {"action": "list"|"create"|"delete", "path": "...", "recursive": false}
    """
    try:
        action = data.get("action", "list")
        path = data.get("path")
        if not path:
            return {"status": "error", "message": "missing required field: path"}
        if not _is_allowed(path):
            return {
                "status": "error",
                "message": "path outside allowed roots (set ATOM_FILE_ROOTS)",
            }

        if action == "list":
            if not os.path.isdir(path):
                return {"status": "error", "message": f"not a directory: {path}"}
            entries = []
            with os.scandir(path) as it:
                for i, entry in enumerate(it):
                    if i >= _MAX_ENTRIES:
                        break
                    entries.append(
                        {
                            "name": entry.name,
                            "type": "dir" if entry.is_dir() else "file",
                            "size": 0 if entry.is_dir() else entry.stat().st_size,
                        }
                    )
            return {
                "status": "success",
                "data": {"entries": entries, "count": len(entries)},
            }

        if action == "create":
            os.makedirs(path, exist_ok=True)
            return {"status": "success", "data": {"path": path, "created": True}}

        if action == "delete":
            if not os.path.exists(path):
                return {"status": "error", "message": f"not found: {path}"}
            if os.path.isdir(path):
                if data.get("recursive"):
                    import shutil

                    shutil.rmtree(path)
                else:
                    os.rmdir(path)  # 非空目录会抛错，防误删
            else:
                os.remove(path)
            return {"status": "success", "data": {"path": path, "deleted": True}}

        return {"status": "error", "message": f"unknown action: {action}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
