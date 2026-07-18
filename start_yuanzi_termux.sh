#!/data/data/com.termux/files/usr/bin/sh
export YUANZI_DB_DIR=/data/data/com.termux/files/home/yuanzi-data
export YUANZI_CORE_URL=http://127.0.0.1:8080
export PYTHONUNBUFFERED=1
mkdir -p "$YUANZI_DB_DIR/logs"
cd /data/data/com.termux/files/home/yuanzi-atoms || exit 1
pkill -9 -f "^[p]ython3 /data/data/com.termux/files/home/yuanzi-atoms/" 2>/dev/null || true
sleep 1
PY=/data/data/com.termux/files/usr/bin/python3
$PY /data/data/com.termux/files/home/yuanzi-atoms/core/main.py >> "$YUANZI_DB_DIR/logs/core.log" 2>&1 &
sleep 2
$PY /data/data/com.termux/files/home/yuanzi-atoms/browser/main.py >> "$YUANZI_DB_DIR/logs/browser.log" 2>&1 &
$PY /data/data/com.termux/files/home/yuanzi-atoms/widget/main.py >> "$YUANZI_DB_DIR/logs/widget.log" 2>&1 &
$PY /data/data/com.termux/files/home/yuanzi-atoms/deepseek/main.py >> "$YUANZI_DB_DIR/logs/deepseek.log" 2>&1 &
$PY /data/data/com.termux/files/home/yuanzi-atoms/obsidian/main.py >> "$YUANZI_DB_DIR/logs/obsidian.log" 2>&1 &
echo "[Yuanzi] atoms started in Termux"
sleep 3
cat "$YUANZI_DB_DIR/logs/core.log" | tail -10

