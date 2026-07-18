#!/usr/bin/env python3
"""批量探测注册原子的健康端点，把状态从"花名册"变成真实可达性。

用法：
    python probe_atoms.py                      # 探测本地 registry.db 全部原子
    python probe_atoms.py --db /path/agent.db  # 指定设备拉下来的 DB
    python probe_atoms.py --atom-id mcp.ecs --atom-id mcp.eks
    python probe_atoms.py --json               # 机器可读输出（含 summary）
    python probe_atoms.py --fail-on-unreachable  # 有不可达原子时退出码 1（监控用）
    python probe_atoms.py --workers 8          # 并发探测（默认 8）
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from migrations import migrate
from registry import list_atoms, probe_atom

DEFAULT_DB = Path(__file__).with_name("registry.db")


def _list_atom_ids(db: str) -> list[str]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        migrate(conn)
        return [a["atom_id"] for a in list_atoms(conn)]
    finally:
        conn.close()


def _probe_one(db: str, atom_id: str, timeout: float) -> dict:
    # 每个线程使用独立连接（sqlite 连接不可跨线程共享）
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return probe_atom(conn, atom_id, timeout=timeout, actor="probe-cli")
    except Exception as exc:  # noqa: BLE001 - 单点失败不应中断批量探测
        return {
            "success": False,
            "atom_id": atom_id,
            "error": "probe_exception",
            "message": str(exc),
        }
    finally:
        conn.close()


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
    parser.add_argument("--json", action="store_true", help="输出 JSON（含 summary）")
    parser.add_argument(
        "--fail-on-unreachable",
        action="store_true",
        help="存在不可达/失败原子时以退出码 1 结束（cron/监控用）",
    )
    parser.add_argument(
        "--workers", type=int, default=8, help="并发探测线程数（默认 8）"
    )
    args = parser.parse_args()

    atom_ids = args.atom_ids or _list_atom_ids(args.db)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(
            pool.map(lambda aid: _probe_one(args.db, aid, args.timeout), atom_ids)
        )

    ok_count = sum(1 for r in results if r.get("ok"))
    summary = {"total": len(results), "reachable": ok_count}

    if args.json:
        print(
            json.dumps(
                {"summary": summary, "results": results}, ensure_ascii=False, indent=2
            )
        )
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
        print("---")
        print(f"{ok_count}/{len(results)} atoms reachable")

    if args.fail_on_unreachable and ok_count < len(results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
