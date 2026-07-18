"""HTTP endpoint health tests for com.example.sum."""
import subprocess
import sys
import time

import pytest
import requests

from server import load_meta

META = load_meta()
PORT = META["runtime"]["port"]
BASE_URL = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def running_server():
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    started = False
    for _ in range(50):
        try:
            requests.get(f"{BASE_URL}/health", timeout=0.5)
            started = True
            break
        except requests.ConnectionError:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
    if not started:
        stdout, stderr = proc.communicate(timeout=5)
        raise RuntimeError(
            f"Server failed to start. stdout={stdout.decode()}, stderr={stderr.decode()}"
        )
    yield proc
    proc.terminate()
    proc.wait()


def test_meta_endpoint(running_server):
    r = requests.get(f"{BASE_URL}/meta")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "com.example.sum"
    assert data["version"] == "0.1.0"
    assert data["type"] == "skill"


def test_health_endpoint(running_server):
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_run_endpoint(running_server):
    r = requests.post(f"{BASE_URL}/run", json={"a": 3, "b": 5})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["data"] == {"result": 8}
