"""Tests for the FastAPI registry API (TestClient, HTTP 探测打桩)."""

from __future__ import annotations

import urllib.error

import pytest
from api import create_app
from fastapi.testclient import TestClient


def _atom(atom_id="com.example.sum", version="1.0.0", functions=("sum",)):
    return {
        "atom_id": atom_id,
        "name": "Sum",
        "version": version,
        "description": "adds numbers",
        "purpose": {"functions": [{"name": f} for f in functions]},
        "architecture": {
            "type": "python_script",
            "runtime": "python3.12",
            "dependencies": [],
        },
        "ownership": {"author": "test", "license": "MIT"},
        "runtime": {"health_url": "http://127.0.0.1:9000/health"},
        "lifecycle": {"status": "submitted"},
    }


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "api-test.db")
    with TestClient(app) as c:
        yield c


def test_health_and_empty_stats(client):
    assert client.get("/health").json() == {"status": "ok"}
    stats = client.get("/stats").json()
    assert stats["total_atoms"] == 0
    assert client.get("/atoms").json() == []


def test_submit_get_review_flow(client):
    r = client.post("/atoms", json=_atom())
    assert r.status_code == 201
    assert r.json()["success"]

    atom = client.get("/atoms/com.example.sum").json()
    assert atom["lifecycle"]["status"] == "submitted"

    r = client.post(
        "/atoms/com.example.sum/review",
        json={"approved": True, "reviewer": "alice", "score": 0.9},
    )
    assert r.json()["status"] == "registered"

    listed = client.get("/atoms", params={"status": "registered"}).json()
    assert len(listed) == 1

    filtered = client.get("/atoms", params={"status": "running"}).json()
    assert filtered == []


def test_get_missing_atom_404(client):
    assert client.get("/atoms/com.example.ghost").status_code == 404


def test_status_transition_validation(client):
    client.post("/atoms", json=_atom())
    client.post("/atoms/com.example.sum/review", json={"approved": True})
    r = client.post("/atoms/com.example.sum/status", json={"status": "flying"})
    assert r.status_code == 409
    r = client.post("/atoms/com.example.sum/status", json={"status": "offline"})
    assert r.json()["new_status"] == "offline"


def test_versions_and_rollback_via_api(client):
    client.post("/atoms", json=_atom(version="1.0.0"))
    client.post("/atoms", json=_atom(version="1.1.0", functions=("sum", "sum_many")))

    versions = client.get("/atoms/com.example.sum/versions").json()
    assert [v["version"] for v in versions] == ["1.0.0", "1.1.0"]

    detail = client.get("/atoms/com.example.sum/versions/1.0.0").json()
    assert [f["name"] for f in detail["purpose"]["functions"]] == ["sum"]

    r = client.post("/atoms/com.example.sum/rollback/1.0.0")
    assert r.json()["success"]
    atom = client.get("/atoms/com.example.sum").json()
    assert atom["version"] == "1.0.0"


def test_probe_endpoints(client, monkeypatch):
    client.post("/atoms", json=_atom())
    client.post("/atoms/com.example.sum/review", json={"approved": True})

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=None: _Resp())
    r = client.post("/atoms/com.example.sum/probe")
    assert r.json()["new_status"] == "running"

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda url, timeout=None: (_ for _ in ()).throw(urllib.error.URLError("down")),
    )
    r = client.post("/probe")
    body = r.json()
    assert body["total"] == 1
    assert body["reachable"] == 0


def test_audit_trail_via_api(client):
    client.post("/atoms", json=_atom())
    client.post("/atoms/com.example.sum/review", json={"approved": True})
    audits = client.get("/audit", params={"atom_id": "com.example.sum"}).json()
    actions = {a["action"] for a in audits}
    assert {"submit", "review"} <= actions


def test_dependencies_endpoint(client):
    client.post("/atoms", json=_atom("com.example.base"))
    child = _atom("com.example.child")
    child["architecture"]["dependencies"] = ["com.example.base"]
    client.post("/atoms", json=child)

    deps = client.get("/atoms/com.example.child/dependencies").json()
    assert deps["ok"]
    assert deps["order"] == ["com.example.base", "com.example.child"]
