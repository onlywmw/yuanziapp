#!/bin/bash
# 启动 Hermes 原子服务
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
export HERMES_DB_DIR="${HERMES_DB_DIR:-/opt/hermes/data}"
export HERMES_CORE_URL="${HERMES_CORE_URL:-http://127.0.0.1:8080}"
export PYTHONUNBUFFERED=1

mkdir -p "$HERMES_DB_DIR"

echo "[Hermes] starting atoms..."

python3 "$DIR/core/main.py" &
sleep 2

python3 "$DIR/browser/main.py" &
python3 "$DIR/widget/main.py" &
python3 "$DIR/deepseek/main.py" &
python3 "$DIR/obsidian/main.py" &

echo "[Hermes] all atoms started"
wait
