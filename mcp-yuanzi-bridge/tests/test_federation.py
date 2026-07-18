"""Tests for the federation registry (M7 task 7.4)."""

from __future__ import annotations

import sqlite3

import pytest
from federation import (
    add_peer,
    export_atoms,
    list_peers,
    remove_peer,
    sync_peer,
)
from migrations import migrate
from registry import get_atom, submit_atom


def _atom(atom_id, author="someone"):
    return {
        "atom_id": atom_id,
        "name": atom_id.split(".")[-1],
        "version": "1.0.0",
        "description": "fed",
        "purpose": {"functions": [{"name": f"f_{atom_id}"}]},
        "architecture": {"type": "t", "runtime": "r", "dependencies": []},
        "ownership": {"author": author, "license": "MIT"},
        "runtime": {"endpoint": "http://127.0.0.1:9999/x"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


def test_peer_crud(conn):
    result = add_peer(conn, "tablet", "http://192.168.1.10:8081/", "trusted")
    assert result["success"]
    assert result["base_url"] == "http://192.168.1.10:8081"  # 尾斜杠归一化

    peers = list_peers(conn)
    assert len(peers) == 1
    assert peers[0]["trust_level"] == "trusted"

    # 同 base_url 重复添加 → 更新而非重复
    add_peer(conn, "tablet2", "http://192.168.1.10:8081", "review")
    assert len(list_peers(conn)) == 1
    assert list_peers(conn)[0]["trust_level"] == "review"

    assert remove_peer(conn, peers[0]["id"])
    assert list_peers(conn) == []
    assert not remove_peer(conn, 999)


def test_add_peer_validation(conn):
    assert not add_peer(conn, "x", "ftp://bad", "trusted")["success"]
    assert not add_peer(conn, "x", "http://ok", "boss")["success"]


def test_export_excludes_runtime(conn):
    submit_atom(conn, _atom("com.example.fed"))
    exported = export_atoms(conn)
    assert len(exported) == 1
    entry = exported[0]
    assert entry["atom_id"] == "com.example.fed"
    assert entry["ownership"]["author"] == "someone"
    assert "runtime" not in entry  # endpoint 是本地概念，不共享
    assert entry["signature_hash"]


def _peer_conn_with_atoms():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    submit_atom(c, _atom("com.example.remote1", author="赵六"))
    submit_atom(c, _atom("com.example.remote2", author="孙七"))
    return c


def test_sync_trusted_peer_auto_approves(conn):
    peer = _peer_conn_with_atoms()
    payload = {"atoms": export_atoms(peer)}
    peer_id = add_peer(conn, "remote", "http://peer.local", "trusted")["id"]

    result = sync_peer(conn, peer_id, http_get=lambda url: payload)
    assert result["success"]
    assert result["imported"] == 2

    atom = get_atom(conn, "com.example.remote1")
    assert atom["lifecycle"]["status"] == "registered"  # trusted 自动审核通过
    assert list_peers(conn)[0]["last_synced_at"]


def test_sync_review_peer_stays_submitted(conn):
    peer = _peer_conn_with_atoms()
    payload = {"atoms": export_atoms(peer)}
    peer_id = add_peer(conn, "remote", "http://peer.local", "review")["id"]

    result = sync_peer(conn, peer_id, http_get=lambda url: payload)
    assert result["imported"] == 2
    assert get_atom(conn, "com.example.remote1")["lifecycle"]["status"] == "submitted"


def test_sync_unknown_peer_refused(conn):
    peer_id = add_peer(conn, "stranger", "http://stranger.local", "unknown")["id"]
    result = sync_peer(conn, peer_id, http_get=lambda url: {"atoms": []})
    assert not result["success"]
    assert result["error"] == "untrusted_peer"


def test_sync_skips_existing_and_duplicates(conn):
    submit_atom(conn, _atom("com.example.remote1"))  # 本地已有
    peer = _peer_conn_with_atoms()
    payload = {"atoms": export_atoms(peer)}
    peer_id = add_peer(conn, "remote", "http://peer.local", "trusted")["id"]

    result = sync_peer(conn, peer_id, http_get=lambda url: payload)
    assert result["imported"] == 1
    assert result["skipped"] == 1


def test_sync_fetch_failure(conn):
    peer_id = add_peer(conn, "dead", "http://dead.local", "trusted")["id"]

    def boom(url):
        raise ConnectionError("unreachable")

    result = sync_peer(conn, peer_id, http_get=boom)
    assert not result["success"]
    assert result["error"] == "fetch_failed"
