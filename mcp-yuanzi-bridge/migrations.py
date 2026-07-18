#!/usr/bin/env python3
"""Yuanzi 注册中心 SQLite schema 迁移系统。

迁移文件：migrations/NNN_description.sql，按编号顺序执行，每个文件一个事务。
已应用记录存在 schema_migrations 表。

旧库兼容（baseline）：如果 atom_registry 表已存在而 schema_migrations 为空，
说明是迁移系统引入前的旧库，001 直接标记为已应用，不再重复建表。

用法：
    python migrations.py --db registry.db            # 执行所有未应用的迁移
    python migrations.py --db registry.db --status   # 只查看状态
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
MIGRATION_FILE_RE = re.compile(r"^(\d{3})_(.+)\.sql$")

MIGRATIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover_migrations(
    migrations_dir: Path = MIGRATIONS_DIR,
) -> List[Tuple[int, str, Path]]:
    """返回 [(version, description, path)]，按版本号排序。"""
    migrations: List[Tuple[int, str, Path]] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = MIGRATION_FILE_RE.match(path.name)
        if not match:
            continue
        migrations.append((int(match.group(1)), match.group(2), path))
    return migrations


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(MIGRATIONS_TABLE_DDL)
    conn.commit()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')",
        (name,),
    ).fetchone()
    return row is not None


def applied_versions(conn: sqlite3.Connection) -> List[int]:
    _ensure_migrations_table(conn)
    rows = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [r[0] for r in rows]


def current_version(conn: sqlite3.Connection) -> int:
    versions = applied_versions(conn)
    return versions[-1] if versions else 0


def pending_migrations(
    conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR
) -> List[Tuple[int, str, Path]]:
    applied = set(applied_versions(conn))
    return [m for m in discover_migrations(migrations_dir) if m[0] not in applied]


def _apply_baseline(conn: sqlite3.Connection, version: int, description: str) -> None:
    """旧库已含业务表：把首个迁移标记为已应用，不执行其 SQL。"""
    conn.execute(
        "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
        (version, f"{description} (baseline)", _now_iso()),
    )
    conn.commit()


def migrate(
    conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR
) -> List[int]:
    """应用所有未执行的迁移，返回本次应用的版本号列表。"""
    _ensure_migrations_table(conn)
    legacy = _table_exists(conn, "atom_registry") and not applied_versions(conn)

    applied_now: List[int] = []
    for version, description, path in pending_migrations(conn, migrations_dir):
        if legacy and version == 1:
            _apply_baseline(conn, version, description)
            applied_now.append(version)
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            # executescript 会先隐式提交挂起事务，因此把脚本本身
            # 包进显式事务；中途失败时回滚，库不停留在半迁移状态。
            conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nCOMMIT;")
        except sqlite3.Error as exc:
            conn.rollback()
            raise RuntimeError(f"Migration {path.name} failed: {exc}") from exc
        with conn:
            conn.execute(
                "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                (version, description, _now_iso()),
            )
        applied_now.append(version)
    return applied_now


def status(conn: sqlite3.Connection) -> dict:
    return {
        "current_version": current_version(conn),
        "applied": applied_versions(conn),
        "pending": [f"{v:03d}_{d}" for v, d, _ in pending_migrations(conn)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite 数据库路径")
    parser.add_argument("--status", action="store_true", help="只查看迁移状态")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        if args.status:
            info = status(conn)
            print(f"current version: {info['current_version']}")
            print(f"applied: {info['applied']}")
            print(f"pending: {info['pending'] or 'none'}")
            return 0
        applied = migrate(conn)
        if applied:
            print(f"Applied migrations: {applied}")
        else:
            print("Already up to date")
        print(f"current version: {current_version(conn)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
