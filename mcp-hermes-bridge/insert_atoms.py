#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 mcp_atoms.json 写入 Hermes core 的 SQLite 数据库"""
import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("HERMES_DB_PATH", "/opt/hermes/data/agent.db")
JSON_PATH = os.environ.get("MCP_ATOMS_JSON", "/opt/hermes/mcp_atoms.json")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        atoms = json.load(f)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atom_id TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            atom_type TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unknown',
            capabilities TEXT DEFAULT '[]',
            updated_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    t = now_utc()
    for atom in atoms:
        cursor.execute("""
            INSERT INTO atoms (atom_id, label, atom_type, endpoint, status, capabilities, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(atom_id) DO UPDATE SET
                label = excluded.label,
                atom_type = excluded.atom_type,
                endpoint = excluded.endpoint,
                status = excluded.status,
                capabilities = excluded.capabilities,
                updated_at = excluded.updated_at
        """, (
            atom["atom_id"],
            atom["label"],
            atom["atom_type"],
            atom["endpoint"],
            atom["status"],
            json.dumps(atom["capabilities"], ensure_ascii=False),
            t,
            t,
        ))

    conn.commit()
    conn.close()
    print(f"[OK] 已导入 {len(atoms)} 个 MCP 服务器原子到 {DB_PATH}")


if __name__ == "__main__":
    main()
