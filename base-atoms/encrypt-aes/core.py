# core.py — system.encrypt-aes AES 加密（基础原子，内置不可注册）
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_ENV = "ATOM_AES_KEY"


def _resolve_key(data):
    """key 来源：入参 key（base64，16/24/32 字节）或 ATOM_AES_KEY 环境变量。"""
    raw = data.get("key") or os.environ.get(_KEY_ENV, "")
    if not raw:
        raise ValueError(f"missing key (pass 'key' or set {_KEY_ENV})")
    key = base64.b64decode(raw)
    if len(key) not in (16, 24, 32):
        raise ValueError("key must decode to 16/24/32 bytes (AES-128/192/256)")
    return key


def handler(data):
    """
    AES-GCM 加密
    :param data: {"text": "...", "key": "<base64>", "aad": "<可选附加数据>"}
    :return: {"ciphertext": "<base64>", "iv": "<base64>", "mode": "GCM"}
    """
    try:
        text = data.get("text")
        if text is None:
            return {"status": "error", "message": "missing required field: text"}
        key = _resolve_key(data)
        aad = data.get("aad")
        aad = aad.encode("utf-8") if aad else None

        iv = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(iv, str(text).encode("utf-8"), aad)
        return {
            "status": "success",
            "data": {
                "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
                "iv": base64.b64encode(iv).decode("utf-8"),
                "mode": "GCM",
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
