"""Schema migration system for the Yuanzi atom registry.

Two complementary layers live here:

1. ``MigrationRunner`` — Python-module migrations (``NNN_name.py`` exposing
   ``upgrade(conn)``) tracked in the ``registry_meta`` key-value table.
   This is the bootstrap layer used by ``registry.ensure_registry_schema()``:
   ``001_initial`` creates the core tables, ``002_add_meta`` adds version
   tracking.  Legacy databases that already have ``atom_registry`` are
   bootstrapped at ``001_initial`` without re-running it.

2. Functional SQL API (``migrate()`` and friends) — numbered
   ``NNN_name.sql`` files applied in order and tracked in the
   ``schema_migrations`` table.  This layer carries the additive M4/M5
   schema (atoms VIEW, atom_versions, function_embeddings) and is used by
   CLI tooling and explicit backfill flows.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

MIGRATION_FILE_RE = re.compile(r"^(\d{3})_([a-z][a-z0-9_]*)\.(?:py|sql)$")
MIGRATIONS_TABLE = "schema_migrations"
META_TABLE = "registry_meta"

_MIGRATIONS_DIR = Path(__file__).parent


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# public functional API — SQL migrations (schema_migrations)
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
        if not m or fpath.suffix != ".sql":
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
    sql = path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.execute(
        f"INSERT INTO {MIGRATIONS_TABLE} (version, description, applied_at) "
        "VALUES (?, ?, ?)",
        (version, path.stem, _now_iso()),
    )
    conn.commit()
    logger.info("Applied migration %d: %s", version, path.name)


# ============================================================
# MigrationRunner — Python-module migrations (registry_meta)
# ============================================================

_PY_MIGRATION_RE = re.compile(r"^(\d{3})_([a-z][a-z0-9_]*)\.py$")


@dataclass
class Migration:
    """A single migration discovered from the filesystem."""

    migration_id: str  # e.g. "001_initial"
    description: str  # module docstring (first line)
    file_path: Path
    module_name: str  # e.g. "migrations.001_initial"


class MigrationRunner:
    """Discovers and applies pending migrations against a SQLite connection."""

    def __init__(self, migrations_dir: Optional[Path] = None) -> None:
        self._migrations_dir = migrations_dir or Path(__file__).parent

    # ---- public API ----

    def ensure_meta_table(self, conn: sqlite3.Connection) -> None:
        """Create the registry_meta table if it does not exist."""
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {META_TABLE} (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()

    def apply_pending(self, conn: sqlite3.Connection) -> List[str]:
        """Apply all unapplied migrations in order. Returns list of applied IDs."""
        self.ensure_meta_table(conn)
        current = self._current_version(conn)

        # Bootstrap: existing database with no version tracking
        if current is None:
            current = self._bootstrap(conn)

        migrations = self._discover()
        applied: List[str] = []
        for m in migrations:
            if self._version_gt(m.migration_id, current):
                logger.info("Applying migration: %s", m.migration_id)
                self._apply_one(conn, m)
                current = m.migration_id
                applied.append(m.migration_id)

        return applied

    def get_current_version(self, conn: sqlite3.Connection) -> Optional[str]:
        """Return the most recently applied migration ID, or None."""
        self.ensure_meta_table(conn)
        return self._current_version(conn)

    # ---- internal ----

    def _discover(self) -> List[Migration]:
        """Find and parse all migration files in the migrations directory."""
        migrations: List[Migration] = []
        for fpath in sorted(self._migrations_dir.iterdir()):
            m = _PY_MIGRATION_RE.match(fpath.name)
            if not m:
                continue
            seq, name = m.group(1), m.group(2)
            migration_id = f"{seq}_{name}"
            mod_name = f"migrations.{seq}_{name}"
            desc = _extract_docstring(fpath)
            migrations.append(
                Migration(
                    migration_id=migration_id,
                    description=desc,
                    file_path=fpath,
                    module_name=mod_name,
                )
            )
        migrations.sort(key=lambda m: m.migration_id)
        return migrations

    def _current_version(self, conn: sqlite3.Connection) -> Optional[str]:
        row = conn.execute(
            f"SELECT value FROM {META_TABLE} WHERE key = 'schema_version'"
        ).fetchone()
        return row[0] if row else None

    def _set_version(self, conn: sqlite3.Connection, version: str) -> None:
        conn.execute(
            f"""INSERT INTO {META_TABLE} (key, value, updated_at)
                VALUES ('schema_version', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value, updated_at=excluded.updated_at""",
            (version, _now_iso()),
        )
        conn.commit()

    def _bootstrap(self, conn: sqlite3.Connection) -> str:
        """Detect existing database state and set initial version."""
        # Check if atom_registry table already exists (pre-migration database)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='atom_registry'"
        ).fetchone()
        if row:
            logger.info("Existing atom_registry detected; bootstrapping at 001_initial")
            self._set_version(conn, "001_initial")
            conn.execute(
                f"""INSERT OR IGNORE INTO {META_TABLE} (key, value, updated_at)
                    VALUES ('schema_bootstrap', ?, ?)""",
                (_now_iso(), _now_iso()),
            )
            conn.commit()
            return "001_initial"
        else:
            self._set_version(conn, "000_empty")
            return "000_empty"

    def _apply_one(self, conn: sqlite3.Connection, migration: Migration) -> None:
        """Load and execute a single migration module."""
        spec = importlib.util.spec_from_file_location(
            migration.module_name, str(migration.file_path)
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load migration {migration.migration_id}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "upgrade"):
            raise RuntimeError(
                f"Migration {migration.migration_id} missing upgrade(conn) function"
            )

        logger.info("Applying migration: %s", migration.migration_id)
        try:
            module.upgrade(conn)
            self._set_version(conn, migration.migration_id)
            logger.info("Applied migration: %s", migration.migration_id)
        except Exception:
            logger.exception(
                "Migration %s failed",
                migration.migration_id,
            )
            raise

    @staticmethod
    def _version_gt(a: str, b: str) -> bool:
        """Compare migration IDs lexicographically: '002_foo' > '001_bar'."""
        return a > b


def _extract_docstring(file_path: Path) -> str:
    """Return the first non-empty line of a Python file's docstring."""
    try:
        text = file_path.read_text(encoding="utf-8")
        start = text.find('"""')
        if start == -1:
            start = text.find("'''")
        if start == -1:
            return ""
        end = text.find(text[start : start + 3], start + 3)
        if end == -1:
            return ""
        doc = text[start + 3 : end].strip()
        return doc.split("\n")[0].strip()
    except Exception:
        return ""
