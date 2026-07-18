"""Tests for the schema migration system."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_bridge = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_bridge))

from migrations import MigrationRunner  # noqa: E402


class TestMigrationRunnerBasics:
    """Core MigrationRunner behavior tests."""

    def test_ensure_meta_table_creates_table(self):
        """registry_meta table is created on first call."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            runner = MigrationRunner()
            runner.ensure_meta_table(conn)
            tables = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='registry_meta'"
            ).fetchall()
            assert len(tables) == 1
        finally:
            conn.close()

    def test_ensure_meta_table_is_idempotent(self):
        """Calling ensure_meta_table twice does not error."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            runner = MigrationRunner()
            runner.ensure_meta_table(conn)
            runner.ensure_meta_table(conn)  # second call
            tables = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='registry_meta'"
            ).fetchall()
            assert len(tables) == 1
        finally:
            conn.close()

    def test_fresh_database_runs_all_migrations(self):
        """A completely empty database runs 001 + 002 + all subsequent."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            runner = MigrationRunner()
            applied = runner.apply_pending(conn)

            # Should have applied at least 001_initial and 002_add_meta
            assert len(applied) >= 2
            assert applied[0] == "001_initial"

            # Verify tables exist
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            assert "atom_registry" in table_names
            assert "atom_audit_log" in table_names
            assert "registry_meta" in table_names
        finally:
            conn.close()

    def test_idempotent_second_run(self):
        """Running apply_pending twice applies no migrations on second run."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            runner = MigrationRunner()
            first = runner.apply_pending(conn)
            assert len(first) >= 2  # 001 + 002

            second = runner.apply_pending(conn)
            assert len(second) == 0
        finally:
            conn.close()

    def test_bootstrap_detects_existing_registry(self):
        """Existing atom_registry table triggers bootstrap at 001_initial."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            # Simulate pre-migration database: atom_registry exists but no meta
            conn.execute("""CREATE TABLE atom_registry (
                    id INTEGER PRIMARY KEY,
                    atom_id TEXT
                )""")
            conn.commit()

            runner = MigrationRunner()
            applied = runner.apply_pending(conn)

            # 001_initial should be skipped (already bootstrapped),
            # but 002_add_meta should be applied
            assert "001_initial" not in applied
            assert "002_add_meta" in applied

            version = runner.get_current_version(conn)
            assert version == "002_add_meta"
        finally:
            conn.close()

    def test_version_tracking(self):
        """schema_version is correctly set after migrations."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            runner = MigrationRunner()
            runner.apply_pending(conn)

            version = runner.get_current_version(conn)
            assert version is not None
            assert version.startswith("00")

            # Verify version stored in registry_meta
            row = conn.execute(
                "SELECT value FROM registry_meta WHERE key = 'schema_version'"
            ).fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_discover_migrations(self):
        """MigrationRunner discovers real migration files."""
        runner = MigrationRunner()
        migrations = runner._discover()
        assert len(migrations) >= 2
        ids = [m.migration_id for m in migrations]
        assert "001_initial" in ids
        assert "002_add_meta" in ids

        # Verify Migration dataclass fields
        for m in migrations:
            assert m.migration_id
            assert m.file_path.exists()
            assert m.module_name.startswith("migrations.")


class TestAtomRegistryAfterMigration:
    """Verify that the atom_registry table works correctly after migration."""

    def test_schema_accepts_full_atom(self):
        """After migration, we can submit and retrieve a full atom."""
        sys.path.insert(0, str(_bridge))
        from registry import (
            compute_signature,
            ensure_registry_schema,
            get_atom,
            submit_atom,
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            ensure_registry_schema(conn)

            atom = {
                "atom_id": "com.test.schema",
                "name": "Schema Test",
                "version": "1.0.0",
                "description": "Testing post-migration schema",
                "purpose": {
                    "summary": "test atom",
                    "functions": [{"name": "test_func"}],
                },
                "architecture": {
                    "type": "function",
                    "runtime": "python3.12",
                    "interface": "std-atom-http-v1",
                },
                "ownership": {"author": "test"},
                "lifecycle": {"status": "submitted"},
            }
            atom["signature"] = {
                "hash": compute_signature(atom),
                "algorithm": "sha256",
            }

            result = submit_atom(conn, atom)
            assert result["success"]

            retrieved = get_atom(conn, "com.test.schema")
            assert retrieved is not None
            assert retrieved["name"] == "Schema Test"
        finally:
            conn.close()
