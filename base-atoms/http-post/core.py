# core.py — system.http-post HTTP POST 请求（基础原子，内置不可注册）
import ipaddress
import os
import socket
from urllib.parse import urlparse

import requests

_ALLOWED_SCHEMES = ("http", "https")
_MAX_BODY = 100 * 1024  # 100KB


def _is_internal_ip(ip):
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _check_url(url):
    """SSRF 防护：协议白名单 + 解析后 IP 过滤（ATOM_HTTP_ALLOW_PRIVATE=1 放行）。"""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return f"scheme '{parsed.scheme or 'none'}' not allowed, only http/https"
    if os.environ.get("ATOM_HTTP_ALLOW_PRIVATE") == "1":
        return None
    host = parsed.hostname
    if not host:
        return "invalid url: missing host"
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return f"cannot resolve host: {host}"
    for info in infos:
        ip = info[4][0]
        if _is_internal_ip(ip):
            return f"refusing to access internal address: {host} ({ip})"
    return None


def handler(data):
    """
    发起 HTTP POST 请求（http/https 公网地址，响应 max 100KB）
    :param data: {"url": "https://...", "headers": {}, "body": str|dict, "timeout": 30}
    """
    try:
        url = data.get("url")
        if not url:
            return {"status": "error", "message": "missing required field: url"}
        url_error = _check_url(url)
        if url_error:
            return {"status": "error", "message": url_error}

        body = data.get("body")
        kwargs = {
            "headers": data.get("headers") or {},
            "timeout": int(data.get("timeout", 30)),
        }
        if isinstance(body, (dict, list)):
            kwargs["json"] = body
        elif body is not None:
            kwargs["data"] = str(body)

        resp = requests.post(url, **kwargs)
        text = resp.text[:_MAX_BODY]
        return {
            "status": "success",
            "data": {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": text,
                "truncated": len(resp.text) > _MAX_BODY,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
