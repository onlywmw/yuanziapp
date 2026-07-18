# server.py
import os

import core  # 导入我们的核心逻辑
from flask import Flask, jsonify, request

app = Flask(__name__)

# --- 网络配置（BUG-005/009）：默认仅回环；端口可用 PORT 环境变量覆盖 ---
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "9003"))


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
    # 这里描述了原子的"身份证"，图谱系统靠这个识别它
    return jsonify(
        {
            "id": "atom.math.sum",
            "name": "Math Sum",
            "type": "function",
            "version": "1.0.0",
            "description": "计算两个数字的和",
            "input_schema": {"a": "float (required)", "b": "float (required)"},
            "output_schema": {"result": "float"},
        }
    )


# --- 标准接口 3：执行入口 ---
@app.route("/run", methods=["POST"])
def run():
    # 获取输入
    input_data = request.json if request.is_json else {}
    # 调用核心逻辑
    result = core.handler(input_data)
    # 返回标准格式
    return jsonify(result)


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
