#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yuanzi Browser Atom - 浏览器能力原子
端口：8083
职责：
  1. 向 yuanzi-core 注册自己
  2. 轮询 /agent/command/poll 获取 browser/* 命令
  3. 暴露 /latest-command 给 Android Widget MCP 查询
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

ATOM_ID = "yuanzi-browser"
LABEL = "浏览器"
ATOM_TYPE = "browser"
PORT = int(os.environ.get("YUANZI_BROWSER_PORT", "8083"))
HOST = os.environ.get("YUANZI_BROWSER_HOST", "127.0.0.1")
CORE_URL = os.environ.get("YUANZI_CORE_URL", "http://127.0.0.1:8080")

latest_command: Optional[Dict[str, Any]] = None
latest_lock = threading.Lock()


def send_json(
    handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.wfile.write(body)


def http_post(url: str, body: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return False, {"error": e.read().decode("utf-8")}
    except Exception as e:
        return False, {"error": str(e)}


def http_get(url: str) -> Tuple[bool, Dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return False, {"error": str(e)}


def register_with_core() -> bool:
    endpoint = f"http://{HOST}:{PORT}"
    ok, resp = http_post(
        f"{CORE_URL}/register",
        {
            "atom_id": ATOM_ID,
            "label": LABEL,
            "type": ATOM_TYPE,
            "endpoint": endpoint,
            "capabilities": [
                "browser/open",
                "browser/navigate",
                "browser/back",
                "browser/forward",
                "browser/reload",
            ],
        },
    )
    print(f"[{ATOM_ID}] register: ok={ok} resp={resp}")
    return ok and resp.get("ok", False)


def poll_loop() -> None:
    global latest_command
    while True:
        ok, resp = http_post(f"{CORE_URL}/agent/command/poll", {})
        if ok and resp.get("ok") and resp.get("data"):
            cmd = resp["data"]
            with latest_lock:
                latest_command = cmd
            print(f"[{ATOM_ID}] got command: {cmd}")
        time.sleep(5)


class BrowserHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{ATOM_ID}] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        if self.path == "/health":
            send_json(
                self, 200, {"ok": True, "data": {"atom": ATOM_ID, "status": "ok"}}
            )
        elif self.path == "/latest-command":
            with latest_lock:
                cmd = latest_command
            if cmd:
                send_json(self, 200, {"ok": True, "data": cmd})
            else:
                send_json(self, 200, {"ok": True, "data": None})
        else:
            send_json(self, 404, {"ok": False, "error": "Not Found"})

    def do_POST(self) -> None:
        if self.path == "/event":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            body = json.loads(raw) if raw else {}
            ok, resp = http_post(f"{CORE_URL}/agent/event", body)
            send_json(
                self,
                200 if ok else 502,
                resp if ok else {"ok": False, "error": str(resp)},
            )
        else:
            send_json(self, 404, {"ok": False, "error": "Not Found"})


def main() -> None:
    # 注册到 core
    for _ in range(10):
        if register_with_core():
            break
        time.sleep(1)

    # 启动轮询线程
    threading.Thread(target=poll_loop, daemon=True).start()

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, PORT), BrowserHandler)
    print(f"[{ATOM_ID}] listening on {HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
