"""`python -m registry`：初始化 registry.db 并打印统计。

原 registry.py 的 __main__ 块平移；库文件路径保持 mcp-yuanzi-bridge/registry.db 不变。
"""

import sqlite3
from pathlib import Path

from .schema import ensure_registry_schema
from .stats import compute_registry_stats

if __name__ == "__main__":
    db_path = Path(__file__).resolve().parent.parent / "registry.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_registry_schema(conn)
    print(f"Registry initialized at {db_path}")
    print("Stats:", compute_registry_stats(conn))
