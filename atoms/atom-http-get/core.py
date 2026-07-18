# core.py
import ipaddress
import os
import socket
from urllib.parse import urlparse

import requests

_ALLOWED_SCHEMES = ("http", "https")


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
    """SSRF 防护（BUG-008）：协议白名单 + 解析后 IP 过滤。

    默认拒绝私网/回环/链路本地等内网地址；本地调试可设
    ATOM_HTTP_GET_ALLOW_PRIVATE=1 显式放行。注意：DNS rebinding
    （解析结果在检查后变化）不在此防护范围内。
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return f"scheme '{parsed.scheme or 'none'}' not allowed, only http/https"

    if os.environ.get("ATOM_HTTP_GET_ALLOW_PRIVATE") == "1":
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
    发起 HTTP GET 请求（仅限 http/https 公网地址）
    :param data: dict, 例如 {"url": "https://api.example.com/data", "headers": {"Accept": "application/json"}, "timeout": 30}
    :return: dict, 包含 status_code/headers/body/text
    """
    try:
        url = data.get("url")
        if not url:
            return {"status": "error", "message": "missing required field: url"}

        url_error = _check_url(url)
        if url_error:
            return {"status": "error", "message": url_error}

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
