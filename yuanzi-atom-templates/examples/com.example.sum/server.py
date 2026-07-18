#!/usr/bin/env python3
"""Standard atom HTTP adapter.

This file is the shell of the atom. It should NOT contain business logic.
Business logic lives in `atom/core.py` (for python_script kernels).
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

META_PATH = Path(__file__).with_name("meta.yaml")


def load_meta() -> dict:
    with open(META_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


META = load_meta()
RUNTIME = META.get("runtime", {})

# BUG-010：请求体上限，防止内存 DoS（可用环境变量调整）
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", 5 * 1024 * 1024))
# BUG-012：默认对外返回通用错误，调试时设 YUANZI_DEBUG=1 才回传异常详情
DEBUG = os.environ.get("YUANZI_DEBUG") == "1"
PORT = int(os.environ.get("PORT", RUNTIME.get("port", 8080)))
HOST = os.environ.get("HOST", RUNTIME.get("host", "127.0.0.1"))

# Import kernel handler based on kernel_type.
kernel_type = META.get("kernel_type", "python_script")
if kernel_type == "python_script":
    from atom.core import handle
else:
    raise NotImplementedError(f"kernel_type '{kernel_type}' is not supported yet.")


class _BodyTooLargeError(Exception):
    def __init__(self, length: int):
        super().__init__(f"body length {length} exceeds limit")
        self.length = length


class AtomHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[{META.get('id', 'atom')}] {self.address_string()} - {fmt % args}")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY_BYTES:
            raise _BodyTooLargeError(length)
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_GET(self) -> None:
        if self.path == "/meta":
            self._send_json(200, META)
        elif self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def _authorized(self) -> bool:
        # 可选鉴权：设置 YUANZI_TOKEN 后，/run 必须携带同名 header
        token = os.environ.get("YUANZI_TOKEN")
        if not token:
            return True
        return self.headers.get("Yuanzi-Token") == token

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            payload = self._read_body()
            result = handle(payload)
            self._send_json(200, {"ok": True, "data": result})
        except _BodyTooLargeError:
            self._send_json(
                413,
                {
                    "ok": False,
                    "error": f"request body too large (limit {MAX_BODY_BYTES} bytes)",
                },
            )
        except Exception as exc:
            # BUG-012：异常详情只进服务端日志，对外返回通用错误
            print(f"[{META.get('id', 'atom')}] handler error: {exc!r}", file=sys.stderr)
            message = str(exc) if DEBUG else "internal error"
            self._send_json(400, {"ok": False, "error": message})


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), AtomHandler)
    print(f"[{META.get('id', 'atom')}] listening on {HOST}:{PORT}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
