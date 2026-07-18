# core.py — system.decrypt-aes AES 解密（基础原子，内置不可注册）
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_ENV = "ATOM_AES_KEY"


def _resolve_key(data):
    raw = data.get("key") or os.environ.get(_KEY_ENV, "")
    if not raw:
        raise ValueError(f"missing key (pass 'key' or set {_KEY_ENV})")
    key = base64.b64decode(raw)
    if len(key) not in (16, 24, 32):
        raise ValueError("key must decode to 16/24/32 bytes (AES-128/192/256)")
    return key


def handler(data):
    """
    AES-GCM 解密
    :param data: {"ciphertext": "<base64>", "iv": "<base64>", "key": "<base64>", "aad": "<可选>"}
    """
    try:
        ciphertext = data.get("ciphertext")
        iv = data.get("iv")
        if not ciphertext or not iv:
            return {
                "status": "error",
                "message": "missing required field: ciphertext/iv",
            }
        key = _resolve_key(data)
        aad = data.get("aad")
        aad = aad.encode("utf-8") if aad else None

        plaintext = AESGCM(key).decrypt(
            base64.b64decode(iv), base64.b64decode(ciphertext), aad
        )
        return {"status": "success", "data": {"text": plaintext.decode("utf-8")}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
