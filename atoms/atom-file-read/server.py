# server.py
import os

import core
from flask import Flask, jsonify, request

app = Flask(__name__)

# --- 网络配置（BUG-005/009）：默认仅回环；端口可用 PORT 环境变量覆盖 ---
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "9001"))


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
            "id": "atom.file.read",
            "name": "File Read",
            "type": "function",
            "version": "1.0.0",
            "description": "读取本地文件内容，支持文本和 base64",
            "input_schema": {
                "path": "string (required, 文件绝对路径)",
                "mode": "string (default: 'text', 可选 'base64')",
                "encoding": "string (default: 'utf-8', text 模式有效)",
                "max_size": "int (default: 5242880, 5MB)",
            },
            "output_schema": {
                "path": "string",
                "size": "int",
                "mode": "string",
                "content": "string",
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
