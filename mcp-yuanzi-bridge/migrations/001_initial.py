"""Migration 001: Initial schema — atom_registry and atom_audit_log tables.

This is the baseline migration that mirrors the current schema used by
all 61 registered atoms. It is idempotent via CREATE TABLE IF NOT EXISTS.
"""

from __future__ import annotations

import sqlite3

MIGRATION_ID = "001_initial"

REGISTRY_TABLE = "atom_registry"
AUDIT_TABLE = "atom_audit_log"


def upgrade(conn: sqlite3.Connection) -> None:
    """Create the initial atom_registry and atom_audit_log tables."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {REGISTRY_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atom_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '1.0.0',
            description TEXT,
            purpose_json TEXT NOT NULL,
            architecture_json TEXT NOT NULL,
            ownership_json TEXT NOT NULL,
            classification_json TEXT,
            compliance_json TEXT,
            quality_json TEXT,
            runtime_json TEXT,
            lifecycle_json TEXT NOT NULL,
            signature_hash TEXT UNIQUE NOT NULL,
            signature_algorithm TEXT NOT NULL DEFAULT 'sha256',
            alias TEXT,
            content_hash TEXT,
            identity_hash TEXT,
            created_at TEXT,
            submitted_at TEXT,
            registered_at TEXT,
            updated_at TEXT,
            reviewed_at TEXT,
            reviewed_by TEXT,
            review_comments TEXT,
            review_score REAL
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atom_id TEXT NOT NULL,
            action TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT,
            actor TEXT,
            detail TEXT,
            created_at TEXT
        )
    """)
