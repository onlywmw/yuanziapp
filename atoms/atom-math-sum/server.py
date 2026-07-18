# server.py
from flask import Flask, request, jsonify
import core  # 导入我们的核心逻辑

app = Flask(__name__)

# --- 标准接口 1：健康检查 ---
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

# --- 标准接口 2：元数据自描述 ---
@app.route('/meta')
def meta():
    # 这里描述了原子的"身份证"，图谱系统靠这个识别它
    return jsonify({
        "id": "atom.math.sum",
        "name": "Math Sum",
        "type": "function",
        "version": "1.0.0",
        "description": "计算两个数字的和",
        "input_schema": {
            "a": "float (required)",
            "b": "float (required)"
        },
        "output_schema": {
            "result": "float"
        }
    })

# --- 标准接口 3：执行入口 ---
@app.route('/run', methods=['POST'])
def run():
    # 获取输入
    input_data = request.json if request.is_json else {}
    # 调用核心逻辑
    result = core.handler(input_data)
    # 返回标准格式
    return jsonify(result)

if __name__ == '__main__':
    # 必须监听 0.0.0.0 才能被外部访问
    app.run(host='0.0.0.0', port=8080)
