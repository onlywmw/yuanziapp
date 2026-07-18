# server.py
from flask import Flask, request, jsonify
import core

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

@app.route('/meta')
def meta():
    return jsonify({
        "id": "atom.file.read",
        "name": "File Read",
        "type": "function",
        "version": "1.0.0",
        "description": "读取本地文件内容，支持文本和 base64",
        "input_schema": {
            "path": "string (required, 文件绝对路径)",
            "mode": "string (default: 'text', 可选 'base64')",
            "encoding": "string (default: 'utf-8', text 模式有效)",
            "max_size": "int (default: 5242880, 5MB)"
        },
        "output_schema": {
            "path": "string",
            "size": "int",
            "mode": "string",
            "content": "string"
        }
    })

@app.route('/run', methods=['POST'])
def run():
    input_data = request.json if request.is_json else {}
    result = core.handler(input_data)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
