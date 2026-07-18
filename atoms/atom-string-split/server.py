# server.py
import core
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/meta")
def meta():
    return jsonify(
        {
            "id": "atom.string.split",
            "name": "String Split",
            "type": "function",
            "version": "1.0.0",
            "description": "按分隔符拆分字符串",
            "input_schema": {
                "text": "string (required)",
                "delimiter": "string (default: ',')",
                "maxsplit": "int (default: -1, 表示不限制)",
            },
            "output_schema": {"parts": "list[string]", "count": "int"},
        }
    )


@app.route("/run", methods=["POST"])
def run():
    input_data = request.json if request.is_json else {}
    result = core.handler(input_data)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
