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
            "max_length": "int (default: 100000, 限制返回文本长度)"
        },
        "output_schema": {
            "status_code": "int",
            "url": "string",
            "headers": "dict",
            "text": "string",
            "encoding": "string"
        }
    })

@app.route('/run', methods=['POST'])
def run():
    input_data = request.json if request.is_json else {}
    result = core.handler(input_data)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
