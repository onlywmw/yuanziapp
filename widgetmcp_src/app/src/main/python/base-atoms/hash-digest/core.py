# core.py — system.hash-digest 哈希计算（基础原子，内置不可注册）
import hashlib

_ALGORITHMS = {"sha256", "sha512", "md5"}


def handler(data):
    """
    计算文本哈希
    :param data: {"text": "...", "algorithm": "sha256"|"sha512"|"md5"}
    """
    try:
        text = data.get("text")
        if text is None:
            return {"status": "error", "message": "missing required field: text"}
        algorithm = data.get("algorithm", "sha256")
        if algorithm not in _ALGORITHMS:
            return {
                "status": "error",
                "message": f"unsupported algorithm: {algorithm} (use sha256/sha512/md5)",
            }
        digest = hashlib.new(algorithm, str(text).encode("utf-8")).hexdigest()
        return {"status": "success", "data": {"digest": digest, "algorithm": algorithm}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
