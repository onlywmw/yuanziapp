# -*- coding: utf-8 -*-
"""
Yuanzi 原子化服务 - 共享 SQLite 数据层
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_DIR = os.environ.get("YUANZI_DB_DIR", "/opt/yuanzi/data")
DB_PATH = os.path.join(DB_DIR, "agent.db")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            tool_id TEXT,
            args_json TEXT DEFAULT '{}',
            result_json TEXT DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS capability_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id TEXT UNIQUE NOT NULL,
            handler_type TEXT NOT NULL,
            target TEXT NOT NULL,
            input_schema TEXT DEFAULT '{}',
            output_schema TEXT DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    cursor.execute(
        """
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
        """
    )

    conn.commit()
    conn.close()


def seed_capabilities() -> None:
    defaults = [
        ("browser/open", "atom", "yuanzi-browser", "{}", "{}"),
        ("browser/navigate", "atom", "yuanzi-browser", "{}", "{}"),
        ("browser/back", "atom", "yuanzi-browser", "{}", "{}"),
        ("browser/forward", "atom", "yuanzi-browser", "{}", "{}"),
        ("browser/reload", "atom", "yuanzi-browser", "{}", "{}"),
        ("widget/list", "atom", "yuanzi-widget", "{}", "{}"),
        ("deepseek/balance", "atom", "yuanzi-deepseek", "{}", "{}"),
        ("obsidian/card", "atom", "yuanzi-obsidian", "{}", "{}"),
    ]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for item in defaults:
        cursor.execute(
            """
            INSERT INTO capability_bindings (tool_id, handler_type, target, input_schema, output_schema)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tool_id) DO NOTHING
            """,
            item,
        )
    conn.commit()
    conn.close()


def _to_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _from_json(s: str) -> Any:
    return json.loads(s) if s else {}


def insert_event(
    source: str,
    tool_id: Optional[str],
    args: Dict[str, Any],
    result: Dict[str, Any],
    status: str = "success",
) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO events (source, tool_id, args_json, result_json, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source, tool_id, _to_json(args), _to_json(result), status, now_utc()),
    )
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return event_id


def poll_pending_browser_command() -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM events
        WHERE status = 'pending' AND tool_id LIKE 'browser/%'
        ORDER BY created_at ASC LIMIT 1
        """
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    event_id = row["id"]
    cursor.execute("UPDATE events SET status = 'delivered' WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    d = dict(row)
    d["args"] = _from_json(d.pop("args_json"))
    d["result"] = _from_json(d.pop("result_json"))
    return d


def mark_event_status(event_id: int, status: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET status = ? WHERE id = ?", (status, event_id))
    conn.commit()
    conn.close()


def list_capabilities() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM capability_bindings WHERE enabled = 1")
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["input_schema"] = _from_json(d["input_schema"])
        d["output_schema"] = _from_json(d["output_schema"])
        result.append(d)
    return result


def register_atom(
    atom_id: str,
    label: str,
    atom_type: str,
    endpoint: str,
    capabilities: List[str],
    status: str = "online",
) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    t = now_utc()
    cursor.execute(
        """
        INSERT INTO atoms (atom_id, label, atom_type, endpoint, status, capabilities, updated_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(atom_id) DO UPDATE SET
            label = excluded.label,
            atom_type = excluded.atom_type,
            endpoint = excluded.endpoint,
            status = excluded.status,
            capabilities = excluded.capabilities,
            updated_at = excluded.updated_at
        """,
        (atom_id, label, atom_type, endpoint, status, _to_json(capabilities), t, t),
    )
    conn.commit()
    conn.close()


def list_atoms() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM atoms ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["capabilities"] = _from_json(d["capabilities"])
        result.append(d)
    return result


def update_atom_status(atom_id: str, status: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE atoms SET status = ?, updated_at = ? WHERE atom_id = ?",
        (status, now_utc(), atom_id),
    )
    conn.commit()
    conn.close()
