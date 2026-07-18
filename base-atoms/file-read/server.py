#!/usr/bin/env python3
"""Standard atom HTTP adapter for system.file-read（基础原子，system 内置）。

端点：/health /meta /run。业务逻辑在 core.py。
加固：默认回环、5MB body 上限（413）、可选 YUANZI_TOKEN、错误详情默认隐藏。
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import handler

META = {
    "id": "system.file-read",
    "name": "File Read",
    "type": "function",
    "version": "1.0.0",
    "author": "system",
    "builtin": True,
    "description": "文件读取（text/base64，沙箱白名单，max 5MB）",
    "input_schema": {
        "path": "string (required)",
        "mode": "text|base64",
        "encoding": "utf-8",
        "max_size": 5242880,
    },
    "output_schema": {"status": "success|error", "data": "object"},
}

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "9002"))
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", 5 * 1024 * 1024))
DEBUG = os.environ.get("YUANZI_DEBUG") == "1"


class _BodyTooLargeError(Exception):
    pass


class AtomHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{META['id']}] {self.address_string()} - {fmt % args}")

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY_BYTES:
            raise _BodyTooLargeError(length)
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def _authorized(self):
        token = os.environ.get("YUANZI_TOKEN")
        if not token:
            return True
        return self.headers.get("Yuanzi-Token") == token

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/meta":
            self._send_json(200, META)
        else:
            self._send_json(404, {"status": "error", "message": "not found"})

    def do_POST(self):
        if self.path != "/run":
            self._send_json(404, {"status": "error", "message": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"status": "error", "message": "unauthorized"})
            return
        try:
            payload = self._read_body()
            self._send_json(200, handler(payload))
        except _BodyTooLargeError:
            self._send_json(
                413,
                {
                    "status": "error",
                    "message": f"request body too large (limit {MAX_BODY_BYTES} bytes)",
                },
            )
        except Exception as exc:
            print(f"[{META['id']}] handler error: {exc!r}", file=sys.stderr)
            message = str(exc) if DEBUG else "internal error"
            self._send_json(400, {"status": "error", "message": message})


def main():
    server = ThreadingHTTPServer((HOST, PORT), AtomHandler)
    print(f"[{META['id']}] listening on {HOST}:{PORT}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
