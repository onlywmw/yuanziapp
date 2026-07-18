"""Security tests for the standard atom server (BUG-009/010/012)."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
import requests
from server import load_meta

META = load_meta()
PORT = META["runtime"]["port"] + 100  # 与 test_health 的实例错开
BASE_URL = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def secured_server():
    env = dict(
        os.environ,
        PORT=str(PORT),
        YUANZI_TOKEN="test-token",
        MAX_BODY_BYTES="64",
    )
    env.pop("YUANZI_DEBUG", None)
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
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


def test_run_requires_token(secured_server):
    r = requests.post(f"{BASE_URL}/run", json={"a": 1, "b": 2})
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_run_with_token(secured_server):
    r = requests.post(
        f"{BASE_URL}/run", json={"a": 1, "b": 2}, headers={"Yuanzi-Token": "test-token"}
    )
    assert r.status_code == 200
    assert r.json()["data"] == {"result": 3}


def test_oversized_body_rejected(secured_server):
    big = "x" * 1024  # 超过 MAX_BODY_BYTES=64
    r = requests.post(
        f"{BASE_URL}/run",
        data=big,
        headers={"Yuanzi-Token": "test-token"},
    )
    assert r.status_code == 413
    assert "too large" in r.json()["error"]


def test_error_details_hidden_by_default(secured_server):
    # 内核抛出 TypeError（字符串不能与数字相加），对外只能是通用错误
    r = requests.post(
        f"{BASE_URL}/run",
        json={"a": "not-a-number"},
        headers={"Yuanzi-Token": "test-token"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "internal error"
