#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes DeepSeek Atom - DeepSeek 能力原子
端口：8084
"""
import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

ATOM_ID = "hermes-deepseek"
LABEL = "DeepSeek"
ATOM_TYPE = "api"
PORT = int(os.environ.get("HERMES_DEEPSEEK_PORT", "8084"))
HOST = os.environ.get("HERMES_DEEPSEEK_HOST", "127.0.0.1")
CORE_URL = os.environ.get("HERMES_CORE_URL", "http://127.0.0.1:8080")


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.wfile.write(body)


def http_post(url: str, body: Dict[str, Any]) -> bool:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8")).get("ok", False)
    except Exception as e:
        print(f"[{ATOM_ID}] http_post error: {e}")
        return False


def register_with_core() -> bool:
    return http_post(
        f"{CORE_URL}/register",
        {
            "atom_id": ATOM_ID,
            "label": LABEL,
            "type": ATOM_TYPE,
            "endpoint": f"http://{HOST}:{PORT}",
            "capabilities": ["deepseek/balance", "deepseek/chat"],
        },
    )


class DeepSeekHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{ATOM_ID}] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        if self.path == "/health":
            send_json(self, 200, {"ok": True, "data": {"atom": ATOM_ID, "status": "ok"}})
        else:
            send_json(self, 404, {"ok": False, "error": "Not Found"})


def main() -> None:
    for _ in range(10):
        if register_with_core():
            break
        time.sleep(1)
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, PORT), DeepSeekHandler)
    print(f"[{ATOM_ID}] listening on {HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
