# server.py
import os

import core
from flask import Flask, jsonify, request

app = Flask(__name__)

# --- 网络配置（BUG-005/009）：默认仅回环；端口可用 PORT 环境变量覆盖 ---
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "9002"))


# --- 可选鉴权：设置 YUANZI_TOKEN 后，/run 必须携带同名 header ---
@app.before_request
def _check_token():
    token = os.environ.get("YUANZI_TOKEN")
    if token and request.path == "/run":
        if request.headers.get("Yuanzi-Token") != token:
            return jsonify({"status": "error", "message": "unauthorized"}), 401
    return None


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/meta")
def meta():
    return jsonify(
        {
            "id": "atom.http.get",
            "name": "HTTP GET",
            "type": "function",
            "version": "1.0.0",
            "description": "发起 HTTP GET 请求并返回响应",
            "input_schema": {
                "url": "string (required)",
                "headers": "dict (optional)",
                "timeout": "int (default: 30)",
                "allow_redirects": "bool (default: True)",
                "max_length": "int (default: 100000, 限制返回文本长度)",
            },
            "output_schema": {
                "status_code": "int",
                "url": "string",
                "headers": "dict",
                "text": "string",
                "encoding": "string",
            },
        }
    )


@app.route("/run", methods=["POST"])
def run():
    input_data = request.json if request.is_json else {}
    result = core.handler(input_data)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
