#!/bin/bash
# 启动 Yuanzi 原子服务
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
export YUANZI_DB_DIR="${YUANZI_DB_DIR:-/opt/yuanzi/data}"
export YUANZI_CORE_URL="${YUANZI_CORE_URL:-http://127.0.0.1:8080}"
export PYTHONUNBUFFERED=1

mkdir -p "$YUANZI_DB_DIR"

echo "[Yuanzi] starting atoms..."

python3 "$DIR/core/main.py" &
sleep 2

python3 "$DIR/browser/main.py" &
python3 "$DIR/widget/main.py" &
python3 "$DIR/deepseek/main.py" &
python3 "$DIR/obsidian/main.py" &

echo "[Yuanzi] all atoms started"
wait
