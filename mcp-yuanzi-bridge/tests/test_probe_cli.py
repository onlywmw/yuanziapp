"""Tests for probe_atoms.py CLI (BUG-021): exit code, json summary, concurrency."""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error

import probe_atoms as cli
import pytest
from migrations import migrate
from registry import review_atom, submit_atom


def _atom(atom_id, url):
    return {
        "atom_id": atom_id,
        "name": atom_id,
        "version": "1.0.0",
        "description": "",
        "purpose": {"functions": [{"name": f"f_{atom_id}"}]},
        "architecture": {"type": "t", "runtime": "r"},
        "ownership": {"author": "t"},
        "runtime": {"health_url": url},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "probe-cli.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    submit_atom(conn, _atom("com.example.up", "http://up.local/health"))
    submit_atom(conn, _atom("com.example.down", "http://down.local/health"))
    review_atom(conn, "com.example.up", approved=True)
    review_atom(conn, "com.example.down", approved=True)
    conn.close()

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(url, timeout=None):
        if "down.local" in url:
            raise urllib.error.URLError("refused")
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return path


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["probe_atoms.py", *argv])
    return cli.main()


def test_exit_code_zero_by_default(db, monkeypatch, capsys):
    rc = _run(monkeypatch, "--db", db)
    assert rc == 0  # 默认不因 unreachable 失败（向后兼容）


def test_fail_on_unreachable_exit_one(db, monkeypatch, capsys):
    rc = _run(monkeypatch, "--db", db, "--fail-on-unreachable")
    assert rc == 1


def test_fail_on_unreachable_all_ok(db, monkeypatch, capsys):
    rc = _run(
        monkeypatch,
        "--db",
        db,
        "--atom-id",
        "com.example.up",
        "--fail-on-unreachable",
    )
    assert rc == 0


def test_json_output_has_summary(db, monkeypatch, capsys):
    _run(monkeypatch, "--db", db, "--json")
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"] == {"total": 2, "reachable": 1}
    assert len(payload["results"]) == 2


def test_concurrent_workers(db, monkeypatch, capsys):
    rc = _run(monkeypatch, "--db", db, "--workers", "4")
    assert rc == 0
    out = capsys.readouterr().out
    assert "1/2 atoms reachable" in out
