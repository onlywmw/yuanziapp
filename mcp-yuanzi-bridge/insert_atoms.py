#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 mcp_atoms.json 写入 Yuanzi core 的 SQLite 数据库"""

import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("YUANZI_DB_PATH", "/opt/yuanzi/data/agent.db")
JSON_PATH = os.environ.get("MCP_ATOMS_JSON", "/opt/yuanzi/mcp_atoms.json")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        atoms = json.load(f)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    from migrations import migrate
    from registry import submit_atom

    conn.row_factory = sqlite3.Row
    migrate(conn)
    ok = 0
    for atom in atoms:
        result = submit_atom(conn, to_registry_atom(atom), actor="insert_atoms")
        if result.get("success"):
            ok += 1
        else:
            print(f"[跳过] {atom['atom_id']}: {result.get('message')}")
    conn.close()
    print(f"完成：{ok}/{len(atoms)} 个原子已提交到注册中心")


if __name__ == "__main__":
    main()


def to_registry_atom(raw: dict) -> dict:
    """把 legacy atoms 行格式转成注册中心 v2 原子（SCHEMA_AUTHORITY 状态 B）。"""
    capabilities = raw.get("capabilities", []) or []
    functions = []
    for cap in capabilities:
        if isinstance(cap, str):
            functions.append({"name": cap.split("/")[-1], "description": cap})
        elif isinstance(cap, dict) and cap.get("name"):
            functions.append(
                {"name": cap["name"], "description": cap.get("description", "")}
            )
    return {
        "atom_id": raw["atom_id"],
        "name": raw.get("label", raw["atom_id"]),
        "version": "1.0.0",
        "description": raw.get("description", "") or raw.get("label", ""),
        "purpose": {"summary": raw.get("label", ""), "functions": functions},
        "architecture": {
            "type": raw.get("atom_type", "mcp-server"),
            "runtime": "python3.10+",
            "dependencies": [],
        },
        "ownership": {"author": "mcp-import", "license": "MIT / project license"},
        "runtime": {"endpoint": raw.get("endpoint", "")},
        "lifecycle": {"status": "submitted"},
    }
