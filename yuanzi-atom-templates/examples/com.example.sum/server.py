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
PORT = int(os.environ.get("PORT", RUNTIME.get("port", 8080)))
HOST = os.environ.get("HOST", RUNTIME.get("host", "0.0.0.0"))

# Import kernel handler based on kernel_type.
kernel_type = META.get("kernel_type", "python_script")
if kernel_type == "python_script":
    from atom.core import handle
else:
    raise NotImplementedError(f"kernel_type '{kernel_type}' is not supported yet.")


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

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            payload = self._read_body()
            result = handle(payload)
            self._send_json(200, {"ok": True, "data": result})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})


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
