# server.py
# 标准原子外壳：网络 / 健康检查 / 元数据 / 执行入口
# 开发新原子时通常不需要修改此文件

from flask import Flask, request, jsonify
import core  # 导入核心逻辑

app = Flask(__name__)

# --- 标准接口 1：健康检查 ---
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

# --- 标准接口 2：元数据自描述 ---
@app.route('/meta')
def meta():
    return jsonify({
        "id": "atom.template.example",     # TODO: 替换为原子唯一 ID
        "name": "Template Atom",           # TODO: 替换为原子名称
        "type": "function",                # TODO: function / skill / agent
        "version": "1.0.0",
        "description": "这是一个原子模板",  # TODO: 替换为描述
        "input_schema": {},                # TODO: 描述输入字段
        "output_schema": {}                # TODO: 描述输出字段
    })

# --- 标准接口 3：执行入口 ---
@app.route('/run', methods=['POST'])
def run():
    input_data = request.json if request.is_json else {}
    result = core.handler(input_data)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
