#!/usr/bin/env python3
"""批量探测注册原子的健康端点，把状态从"花名册"变成真实可达性。

用法：
    python probe_atoms.py                      # 探测本地 registry.db 全部原子
    python probe_atoms.py --db /path/agent.db  # 指定设备拉下来的 DB
    python probe_atoms.py --atom-id mcp.ecs --atom-id mcp.eks
    python probe_atoms.py --json               # 机器可读输出
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from migrations import migrate
from registry import probe_atoms

DEFAULT_DB = Path(__file__).with_name("registry.db")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 数据库路径")
    parser.add_argument("--timeout", type=float, default=2.0, help="单次探测超时（秒）")
    parser.add_argument(
        "--atom-id",
        action="append",
        dest="atom_ids",
        help="只探测指定原子（可重复），缺省探测全部",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    migrate(conn)

    results = probe_atoms(conn, atom_ids=args.atom_ids, timeout=args.timeout)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            if not r.get("success"):
                print(f"ERROR  {r.get('atom_id', ''):45s} {r.get('message')}")
                continue
            mark = "OK  " if r["ok"] else "DOWN"
            print(
                f"{mark}  {r['atom_id']:45s} {r['old_status'] or '-':>12s} -> "
                f"{r['new_status']:<12s} {r['probe_status']} {r['latency_ms']}ms"
            )
        ok_count = sum(1 for r in results if r.get("ok"))
        print("---")
        print(f"{ok_count}/{len(results)} atoms reachable")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
