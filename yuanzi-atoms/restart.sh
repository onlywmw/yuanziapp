#!/bin/bash
# 重启 Yuanzi 原子服务
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
export YUANZI_DB_DIR="${YUANZI_DB_DIR:-/opt/yuanzi/data}"
export YUANZI_CORE_URL="${YUANZI_CORE_URL:-http://127.0.0.1:8080}"
export PYTHONUNBUFFERED=1

echo "[Yuanzi] stopping atoms..."
# 用正则避免 pkill 匹配到自身命令行
pkill -9 -f "^[p]ython3 /opt/yuanzi/" 2>/dev/null || true
sleep 1

mkdir -p "$YUANZI_DB_DIR"
LOG_DIR="${YUANZI_DB_DIR}/logs"
mkdir -p "$LOG_DIR"

echo "[Yuanzi] starting core..."
setsid python3 "$DIR/core/main.py" >> "$LOG_DIR/core.log" 2>&1 &
sleep 2

echo "[Yuanzi] starting browser atom..."
setsid python3 "$DIR/browser/main.py" >> "$LOG_DIR/browser.log" 2>&1 &

echo "[Yuanzi] starting widget atom..."
setsid python3 "$DIR/widget/main.py" >> "$LOG_DIR/widget.log" 2>&1 &

echo "[Yuanzi] starting deepseek atom..."
setsid python3 "$DIR/deepseek/main.py" >> "$LOG_DIR/deepseek.log" 2>&1 &

echo "[Yuanzi] starting obsidian atom..."
setsid python3 "$DIR/obsidian/main.py" >> "$LOG_DIR/obsidian.log" 2>&1 &

echo "[Yuanzi] atoms restarted"
