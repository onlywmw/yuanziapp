# server.py
# 标准原子外壳：网络 / 健康检查 / 元数据 / 执行入口
# 开发新原子时通常不需要修改此文件

import os

import core  # 导入核心逻辑
from flask import Flask, jsonify, request

app = Flask(__name__)

# --- 网络配置（BUG-005/009）：默认仅回环；端口可用 PORT 环境变量覆盖 ---
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "9005"))


# --- 可选鉴权：设置 YUANZI_TOKEN 后，/run 必须携带同名 header ---
@app.before_request
def _check_token():
    token = os.environ.get("YUANZI_TOKEN")
    if token and request.path == "/run":
        if request.headers.get("Yuanzi-Token") != token:
            return jsonify({"status": "error", "message": "unauthorized"}), 401
    return None


# --- 标准接口 1：健康检查 ---
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


# --- 标准接口 2：元数据自描述 ---
@app.route("/meta")
def meta():
    return jsonify(
        {
            "id": "atom.template.example",  # TODO: 替换为原子唯一 ID
            "name": "Template Atom",  # TODO: 替换为原子名称
            "type": "function",  # TODO: function / skill / agent
            "version": "1.0.0",
            "description": "这是一个原子模板",  # TODO: 替换为描述
            "input_schema": {},  # TODO: 描述输入字段
            "output_schema": {},  # TODO: 描述输出字段
        }
    )


# --- 标准接口 3：执行入口 ---
@app.route("/run", methods=["POST"])
def run():
    input_data = request.json if request.is_json else {}
    result = core.handler(input_data)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
