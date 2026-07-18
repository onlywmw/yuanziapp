"""Schema migration system for the Yuanzi atom registry.

SQL-based migrations in this directory (``NNN_name.sql``) are applied in
order via ``migrate(conn)``.  A ``schema_migrations`` table tracks which
versions have been applied.

Safety properties:
- 旧库 baseline：atom_registry 已存在而 schema_migrations 为空时，001
  只记录不执行（迁移系统引入前的库）。
- 每个迁移包在显式事务中执行，失败回滚，库不会停留在半迁移状态。

Also provides a ``MigrationRunner`` class that wraps the same logic for
use by ``registry.ensure_registry_schema()``.

CLI：
    python -m migrations --db registry.db [--status]
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

MIGRATION_FILE_RE = re.compile(r"^(\d{3})_(.+)\.sql$")
MIGRATIONS_TABLE = "schema_migrations"

MIGRATIONS_DIR = Path(__file__).parent
# 兼容旧引用
_MIGRATIONS_DIR = MIGRATIONS_DIR


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# public functional API — used by api.py and tests
# ============================================================


def migrate(conn: sqlite3.Connection) -> List[int]:
    """Apply all pending migrations, return list of newly-applied versions.

    旧库 baseline：有业务表但无迁移记录时，001 只标记不执行。
    """
    ensure_tracking_table(conn)
    legacy = _table_exists(conn, "atom_registry") and not applied_versions(conn)

    newly_applied: List[int] = []
    for version, name, path in discover_migrations():
        if version in set(applied_versions(conn)):
            continue
        if legacy and version == 1:
            _apply_baseline(conn, version, name)
        else:
            _apply_sql_file(conn, version, path)
        newly_applied.append(version)

    return newly_applied


def current_version(conn: sqlite3.Connection) -> int:
    """Return the latest applied migration version, or 0 if none."""
    versions = applied_versions(conn)
    return versions[-1] if versions else 0


def applied_versions(conn: sqlite3.Connection) -> List[int]:
    """Return sorted list of all applied migration versions."""
    ensure_tracking_table(conn)
    rows = conn.execute(
        f"SELECT version FROM {MIGRATIONS_TABLE} ORDER BY version"
    ).fetchall()
    return [r[0] for r in rows]


def pending_migrations(conn: sqlite3.Connection) -> List[int]:
    """Return list of migration versions not yet applied."""
    applied = set(applied_versions(conn))
    return [v for v, _, _ in discover_migrations() if v not in applied]


def discover_migrations() -> List[Tuple[int, str, Path]]:
    """Return sorted list of (version, name, file_path) for all .sql migrations."""
    migrations: List[Tuple[int, str, Path]] = []
    for fpath in sorted(MIGRATIONS_DIR.iterdir()):
        m = MIGRATION_FILE_RE.match(fpath.name)
        if not m:
            continue
        migrations.append((int(m.group(1)), m.group(2), fpath))
    migrations.sort(key=lambda x: x[0])
    return migrations


def ensure_tracking_table(conn: sqlite3.Connection) -> None:
    """Create the schema_migrations table if it does not exist."""
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            version     INTEGER PRIMARY KEY,
            description TEXT,
            applied_at  TEXT NOT NULL
        )
    """
    )
    conn.commit()


def status(conn: sqlite3.Connection) -> dict:
    """迁移状态总览（CLI --status 用）。"""
    return {
        "current_version": current_version(conn),
        "applied": applied_versions(conn),
        "pending": pending_migrations(conn),
    }


# ============================================================
# internal helpers
# ============================================================


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')",
        (name,),
    ).fetchone()
    return row is not None


def _apply_baseline(conn: sqlite3.Connection, version: int, description: str) -> None:
    """旧库已含业务表：把首个迁移标记为已应用，不执行其 SQL。"""
    conn.execute(
        f"INSERT INTO {MIGRATIONS_TABLE} (version, description, applied_at) "
        "VALUES (?, ?, ?)",
        (version, f"{description} (baseline)", _now_iso()),
    )
    conn.commit()
    logger.info("Baselined migration %d (legacy DB)", version)


def _apply_sql_file(conn: sqlite3.Connection, version: int, path: Path) -> None:
    """Execute a .sql migration file in an explicit transaction and record it."""
    sql = path.read_text(encoding="utf-8")
    try:
        # executescript 会先隐式提交挂起事务，因此把脚本本身包进显式事务；
        # 中途失败时回滚，库不停留在半迁移状态。
        conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nCOMMIT;")
    except sqlite3.Error as exc:
        conn.rollback()
        raise RuntimeError(f"Migration {path.name} failed: {exc}") from exc
    with conn:
        conn.execute(
            f"INSERT INTO {MIGRATIONS_TABLE} (version, description, applied_at) "
            "VALUES (?, ?, ?)",
            (version, path.stem, _now_iso()),
        )
    logger.info("Applied migration %d: %s", version, path.name)


# ============================================================
# MigrationRunner — wraps the functional API for registry.py
# ============================================================


class MigrationRunner:
    """Wraps ``migrate()`` for use by ``registry.ensure_registry_schema()``."""

    def apply_pending(self, conn: sqlite3.Connection) -> List[str]:
        """Apply pending migrations, return string IDs for logging."""
        versions = migrate(conn)
        return [f"{v:03d}" for v in versions]

    def get_current_version(self, conn: sqlite3.Connection) -> Optional[str]:
        """Return current migration version as a string."""
        v = current_version(conn)
        return f"{v:03d}" if v > 0 else None

    def ensure_meta_table(self, conn: sqlite3.Connection) -> None:
        """Create tracking table (alias for functional API)."""
        ensure_tracking_table(conn)

    def _discover(self) -> list:
        """Discover migrations (for backward compat with tests)."""
        return discover_migrations()


# ============================================================
# CLI
# ============================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="Yuanzi registry schema migrations")
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
