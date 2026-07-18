"""Schema migration system for the Yuanzi atom registry.

SQL-based migrations in this directory (``NNN_name.sql``) are applied in
order via ``migrate(conn)``.  A ``schema_migrations`` table tracks which
versions have been applied.

Also provides a ``MigrationRunner`` class that wraps the same logic for
use by ``registry.ensure_registry_schema()``.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

MIGRATION_FILE_RE = re.compile(r"^(\d{3})_([a-z][a-z0-9_]*)\.(?:py|sql)$")
MIGRATIONS_TABLE = "schema_migrations"

_MIGRATIONS_DIR = Path(__file__).parent


# ============================================================
# public functional API — used by api.py and tests
# ============================================================


def migrate(conn: sqlite3.Connection) -> List[int]:
    """Apply all pending migrations, return list of newly-applied versions."""
    ensure_tracking_table(conn)
    applied = set(applied_versions(conn))
    discovered = discover_migrations()
    newly_applied: List[int] = []

    for version, _name, path in discovered:
        if version in applied:
            continue
        _apply_sql_file(conn, version, path)
        newly_applied.append(version)

    return newly_applied


def current_version(conn: sqlite3.Connection) -> int:
    """Return the latest applied migration version, or 0 if none."""
    ensure_tracking_table(conn)
    row = conn.execute(f"SELECT MAX(version) FROM {MIGRATIONS_TABLE}").fetchone()
    return row[0] if row[0] is not None else 0


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
    for fpath in sorted(_MIGRATIONS_DIR.iterdir()):
        m = MIGRATION_FILE_RE.match(fpath.name)
        if not m:
            continue
        version = int(m.group(1))
        name = m.group(2)
        migrations.append((version, name, fpath))
    migrations.sort(key=lambda x: x[0])
    return migrations


def ensure_tracking_table(conn: sqlite3.Connection) -> None:
    """Create the schema_migrations table if it does not exist."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            version     INTEGER PRIMARY KEY,
            description TEXT,
            applied_at  TEXT NOT NULL
        )
    """)
    conn.commit()


# ============================================================
# internal helpers
# ============================================================


def _apply_sql_file(conn: sqlite3.Connection, version: int, path: Path) -> None:
    """Execute a .sql migration file and record it."""
    from datetime import datetime, timezone

    sql = path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.execute(
        f"INSERT INTO {MIGRATIONS_TABLE} (version, description, applied_at) "
        "VALUES (?, ?, ?)",
        (version, path.stem, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
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
