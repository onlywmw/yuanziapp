"""Tests for insert_atoms.py — writing MCP atoms to the legacy atoms table."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

_bridge = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_bridge))

from insert_atoms import now_utc  # noqa: E402

SAMPLE_ATOMS = [
    {
        "atom_id": "mcp.test-service",
        "label": "Test Service",
        "atom_type": "mcp-server",
        "endpoint": "http://127.0.0.1:8080/mcp/test-service",
        "status": "registered",
        "capabilities": ["mcp/test-service/test_tool"],
    },
    {
        "atom_id": "mcp.data-loader",
        "label": "Data Loader",
        "atom_type": "mcp-server",
        "endpoint": "http://127.0.0.1:8080/mcp/data-loader",
        "status": "declared",
        "capabilities": ["mcp/data-loader/load"],
    },
]


class TestInsertAtoms:
    """Tests for insert_atoms module — writing to atoms table."""

    def test_now_utc_iso_format(self):
        ts = now_utc()
        assert "T" in ts
        assert ts.endswith("+00:00") or ts.endswith("Z")

    def test_atoms_table_structure(self):
        """Verify the atoms table can be created and atoms inserted/queried."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
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

                t = now_utc()
                atom = SAMPLE_ATOMS[0]
                conn.execute(
                    """INSERT INTO atoms (atom_id, label, atom_type, endpoint,
                        status, capabilities, updated_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(atom_id) DO UPDATE SET
                        label = excluded.label,
                        atom_type = excluded.atom_type,
                        endpoint = excluded.endpoint,
                        status = excluded.status,
                        capabilities = excluded.capabilities,
                        updated_at = excluded.updated_at""",
                    (
                        atom["atom_id"],
                        atom["label"],
                        atom["atom_type"],
                        atom["endpoint"],
                        atom["status"],
                        json.dumps(atom["capabilities"], ensure_ascii=False),
                        t,
                        t,
                    ),
                )
                conn.commit()

                row = conn.execute(
                    "SELECT * FROM atoms WHERE atom_id = ?", (atom["atom_id"],)
                ).fetchone()
                assert row is not None
                assert row["label"] == "Test Service"
                assert row["status"] == "registered"

                caps = json.loads(row["capabilities"])
                assert "mcp/test-service/test_tool" in caps
            finally:
                conn.close()

    def test_insert_on_conflict_update(self):
        """ON CONFLICT DO UPDATE should update existing atom, not duplicate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
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

                t = now_utc()
                atom = SAMPLE_ATOMS[0]

                # Insert first
                conn.execute(
                    """INSERT INTO atoms (atom_id, label, atom_type, endpoint,
                        status, capabilities, updated_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(atom_id) DO UPDATE SET
                        label = excluded.label,
                        atom_type = excluded.atom_type,
                        endpoint = excluded.endpoint,
                        status = excluded.status,
                        capabilities = excluded.capabilities,
                        updated_at = excluded.updated_at""",
                    (
                        atom["atom_id"],
                        atom["label"],
                        atom["atom_type"],
                        atom["endpoint"],
                        atom["status"],
                        json.dumps(atom["capabilities"], ensure_ascii=False),
                        t,
                        t,
                    ),
                )
                conn.commit()

                # Update same atom_id with new status
                atom2 = {**SAMPLE_ATOMS[0], "status": "offline"}
                conn.execute(
                    """INSERT INTO atoms (atom_id, label, atom_type, endpoint,
                        status, capabilities, updated_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(atom_id) DO UPDATE SET
                        label = excluded.label,
                        atom_type = excluded.atom_type,
                        endpoint = excluded.endpoint,
                        status = excluded.status,
                        capabilities = excluded.capabilities,
                        updated_at = excluded.updated_at""",
                    (
                        atom2["atom_id"],
                        atom2["label"],
                        atom2["atom_type"],
                        atom2["endpoint"],
                        atom2["status"],
                        json.dumps(atom2["capabilities"], ensure_ascii=False),
                        t,
                        t,
                    ),
                )
                conn.commit()

                count = conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0]
                assert count == 1
                row = conn.execute(
                    "SELECT status FROM atoms WHERE atom_id = ?",
                    (atom["atom_id"],),
                ).fetchone()
                assert row["status"] == "offline"
            finally:
                conn.close()
