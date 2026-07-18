#!/data/data/com.termux/files/usr/bin/sh
export HERMES_DB_DIR=/data/data/com.termux/files/home/hermes-data
export HERMES_CORE_URL=http://127.0.0.1:8080
export PYTHONUNBUFFERED=1
mkdir -p "$HERMES_DB_DIR/logs"
cd /data/data/com.termux/files/home/hermes-atoms || exit 1
pkill -9 -f "^[p]ython3 /data/data/com.termux/files/home/hermes-atoms/" 2>/dev/null || true
sleep 1
PY=/data/data/com.termux/files/usr/bin/python3
$PY /data/data/com.termux/files/home/hermes-atoms/core/main.py >> "$HERMES_DB_DIR/logs/core.log" 2>&1 &
sleep 2
$PY /data/data/com.termux/files/home/hermes-atoms/browser/main.py >> "$HERMES_DB_DIR/logs/browser.log" 2>&1 &
$PY /data/data/com.termux/files/home/hermes-atoms/widget/main.py >> "$HERMES_DB_DIR/logs/widget.log" 2>&1 &
$PY /data/data/com.termux/files/home/hermes-atoms/deepseek/main.py >> "$HERMES_DB_DIR/logs/deepseek.log" 2>&1 &
$PY /data/data/com.termux/files/home/hermes-atoms/obsidian/main.py >> "$HERMES_DB_DIR/logs/obsidian.log" 2>&1 &
echo "[Hermes] atoms started in Termux"
sleep 3
cat "$HERMES_DB_DIR/logs/core.log" | tail -10

