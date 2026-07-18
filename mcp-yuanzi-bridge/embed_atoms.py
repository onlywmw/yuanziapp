#!/usr/bin/env python3
"""批量生成函数 embedding（M5 任务 5.1）。

用法：
    python embed_atoms.py --db registry.db --provider mock
    python embed_atoms.py --db agent.db --provider openai \
        # 需 EMBEDDING_API_BASE / EMBEDDING_API_KEY / EMBEDDING_MODEL
    python embed_atoms.py --db registry.db --atom-id mcp.ecs
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from embeddings import embed_all_functions, embed_atom_functions, get_provider
from migrations import migrate

DEFAULT_DB = Path(__file__).with_name("registry.db")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 数据库路径")
    parser.add_argument(
        "--provider",
        default="mock",
        choices=["mock", "openai"],
        help="embedding 提供者（默认 mock 离线）",
    )
    parser.add_argument(
        "--atom-id",
        action="append",
        dest="atom_ids",
        help="只处理指定原子（可重复），缺省处理全部",
    )
    parser.add_argument("--dim", type=int, default=128, help="mock provider 维度")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    migrate(conn)

    provider = get_provider(
        args.provider, **({"dim": args.dim} if args.provider == "mock" else {})
    )

    if args.atom_ids:
        counts = {
            aid: embed_atom_functions(conn, aid, provider) for aid in args.atom_ids
        }
    else:
        counts = embed_all_functions(conn, provider)

    total = sum(counts.values())
    for atom_id, count in sorted(counts.items()):
        print(f"{atom_id:50s} {count} functions")
    print("---")
    print(
        f"Embedded {total} functions across {len(counts)} atoms "
        f"(provider={provider.name}, model={provider.model})"
    )
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
