#!/data/data/com.termux/files/usr/bin/sh
# Start Yuanzi atoms inside Termux.
# This script is intended to live at the project root on the tablet.

export YUANZI_PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
export YUANZI_DB_DIR="${YUANZI_DB_DIR:-/data/data/com.termux/files/home/yuanzi-data}"
export YUANZI_CORE_URL="${YUANZI_CORE_URL:-http://127.0.0.1:8080}"
export PYTHONUNBUFFERED=1

mkdir -p "$YUANZI_DB_DIR/logs"
cd "${YUANZI_PROJECT_DIR}/yuanzi-atoms" || exit 1

pkill -9 -f "python3 .*${YUANZI_PROJECT_DIR}/yuanzi-atoms/" 2>/dev/null || true
sleep 1

PY=/data/data/com.termux/files/usr/bin/python3
$PY "${YUANZI_PROJECT_DIR}/yuanzi-atoms/core/main.py" >> "$YUANZI_DB_DIR/logs/core.log" 2>&1 &
sleep 2
$PY "${YUANZI_PROJECT_DIR}/yuanzi-atoms/browser/main.py" >> "$YUANZI_DB_DIR/logs/browser.log" 2>&1 &
$PY "${YUANZI_PROJECT_DIR}/yuanzi-atoms/widget/main.py" >> "$YUANZI_DB_DIR/logs/widget.log" 2>&1 &
$PY "${YUANZI_PROJECT_DIR}/yuanzi-atoms/deepseek/main.py" >> "$YUANZI_DB_DIR/logs/deepseek.log" 2>&1 &
$PY "${YUANZI_PROJECT_DIR}/yuanzi-atoms/obsidian/main.py" >> "$YUANZI_DB_DIR/logs/obsidian.log" 2>&1 &

echo "[Yuanzi] atoms started in Termux (project: $YUANZI_PROJECT_DIR)"
sleep 3
tail -10 "$YUANZI_DB_DIR/logs/core.log"
