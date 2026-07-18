"""Migration 002: Add registry_meta table for schema version tracking.

This is the first migration that actually changes the database for
pre-existing installations (after bootstrap detects 001_initial).
"""

from __future__ import annotations

import sqlite3

MIGRATION_ID = "002_add_meta"

META_TABLE = "registry_meta"


def upgrade(conn: sqlite3.Connection) -> None:
    """Create the registry_meta table (key-value metadata store)."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {META_TABLE} (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
