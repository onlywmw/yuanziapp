"""`yuanzi atom init` 脚手架模板（原子基座夯实 v2.1 §7）。

固定排序 7 项，所有原子一致：
    core.py / meta.json / server.py / Dockerfile / requirements.txt /
    tests/test_smoke.py / tests/test_contract.py

模板占位符：``__ATOM_ID__``（反向域名 id）、``__ATOM_NAME__``（id 末段）。
server.py 沿用 base-atoms 加固骨架：默认回环 127.0.0.1、5MB body 上限（413）、
可选 YUANZI_TOKEN 鉴权、错误详情默认隐藏（YUANZI_DEBUG=1 时显示）。
meta.json 遵循跨代理契约：I/O 类型小写三值 ["json", "stream", "file_ref"]，
副作用标签字段 "side_effect"，枚举 ["pure", "impure"]，默认 "impure"。
"""

from __future__ import annotations

_CORE_PY = '''"""__ATOM_NAME__ 原子业务逻辑（yuanzi atom init 脚手架生成）。

约定：handler(data) 接收 dict，返回统一信封：
  成功: {"status": "success", "data": {...}}
  失败: {"status": "error", "message": "..."}
"""

from __future__ import annotations

from typing import Any


def handler(data: dict[str, Any]) -> dict[str, Any]:
    """原子入口：处理输入并返回统一信封。

    :param data: 请求体 JSON 对象，字段约束见 meta.json 的 input.schema
    :return: {"status": "success", "data": {...}}
             或 {"status": "error", "message": "..."}

    示例：
        >>> handler({"city": "Shanghai"})
        {'status': 'success', 'data': {'echo': {'city': 'Shanghai'}}}
    """
    # TODO: 在此实现业务逻辑；以下为最小回声示例，保证脚手架开箱可测。
    return {"status": "success", "data": {"echo": data}}
'''

_META_JSON = '''{
  "id": "__ATOM_ID__",
  "name": "__ATOM_NAME__",
  "version": "0.1.0",
  "description": "TODO: 一句话描述这个原子做什么",
  "type": "function",
  "side_effect": "impure",
  "input": {
    "type": "json",
    "schema": {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "title": "__ATOM_NAME__ input",
      "type": "object",
      "properties": {},
      "required": [],
      "additionalProperties": true
    }
  },
  "output": {
    "type": "json",
    "schema": {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "title": "__ATOM_NAME__ output",
      "type": "object",
      "properties": {
        "status": { "type": "string", "enum": ["success", "error"] }
      },
      "required": ["status"],
      "additionalProperties": true
    }
  },
  "runtime": {
    "interface": "std-atom-http-v1",
    "host": "127.0.0.1",
    "port": 8080,
    "state": "stateless",
    "execution": "sync"
  }
}
'''

_SERVER_PY = '''#!/usr/bin/env python3
"""__ATOM_ID__ 标准原子 HTTP 适配器（yuanzi atom init 脚手架生成）。

端点：/health /meta /run。业务逻辑在 core.py，元数据在 meta.json。
加固：默认回环 127.0.0.1、5MB body 上限（413）、可选 YUANZI_TOKEN 鉴权、
错误详情默认隐藏（YUANZI_DEBUG=1 时显示）。
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core import handler

META = json.loads(Path(__file__).with_name("meta.json").read_text(encoding="utf-8"))

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
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
'''

_DOCKERFILE = '''FROM python:3.12-slim
WORKDIR /atom
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
# 容器内监听所有接口；容器外本地运行默认仍为 127.0.0.1（见 server.py）
ENV HOST=0.0.0.0 PORT=8080
EXPOSE 8080
CMD ["python", "server.py"]
'''

_REQUIREMENTS = '''# 运行期零第三方依赖（server.py 仅用标准库 http.server）
# 以下为测试依赖：tests/ 下的 smoke 与 contract 用例需要
pytest>=7.0
jsonschema>=4.0
'''

_TEST_SMOKE = '''"""__ATOM_NAME__ smoke 测试：handler 基本路径。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import handler


def test_handler_echo_success():
    result = handler({"city": "Shanghai"})
    assert result["status"] == "success"
    assert result["data"]["echo"] == {"city": "Shanghai"}


def test_handler_empty_input():
    result = handler({})
    assert result["status"] == "success"
'''

_TEST_CONTRACT = '''"""__ATOM_NAME__ contract 测试：meta.json 合法性与 v2.1 契约。

契约要点（与注册侧一致）：
  - I/O 类型小写三值：json / stream / file_ref，默认 json
  - 副作用标签字段 side_effect，枚举 pure / impure，默认 impure
"""

import json
from pathlib import Path

import pytest

META_PATH = Path(__file__).resolve().parents[1] / "meta.json"

IO_TYPES = {"json", "stream", "file_ref"}
SIDE_EFFECTS = {"pure", "impure"}
REQUIRED_FIELDS = (
    "id",
    "name",
    "version",
    "description",
    "type",
    "side_effect",
    "input",
    "output",
)


@pytest.fixture(scope="module")
def meta():
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def test_meta_required_fields(meta):
    for key in REQUIRED_FIELDS:
        assert key in meta, f"meta.json 缺少必填字段: {key}"


def test_meta_io_types(meta):
    assert meta["input"]["type"] in IO_TYPES
    assert meta["output"]["type"] in IO_TYPES


def test_meta_side_effect(meta):
    assert meta["side_effect"] in SIDE_EFFECTS


def test_meta_schemas_are_valid_json_schema(meta):
    jsonschema = pytest.importorskip("jsonschema")
    for direction in ("input", "output"):
        schema = meta[direction]["schema"]
        jsonschema.validators.validator_for(schema).check_schema(schema)
'''

# v2.1 §7 固定排序：一条命令，7 个文件，所有原子一致。
ATOM_FILES: tuple[tuple[str, str], ...] = (
    ("core.py", _CORE_PY),
    ("meta.json", _META_JSON),
    ("server.py", _SERVER_PY),
    ("Dockerfile", _DOCKERFILE),
    ("requirements.txt", _REQUIREMENTS),
    ("tests/test_smoke.py", _TEST_SMOKE),
    ("tests/test_contract.py", _TEST_CONTRACT),
)
