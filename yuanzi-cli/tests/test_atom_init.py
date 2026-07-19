"""Tests for the `yuanzi atom init` command (v2.1 §7 fixed 7-file scaffold)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from yuanzi_cli.atom_templates import ATOM_FILES
from yuanzi_cli.main import app

runner = CliRunner()

# v2.1 §7 固定排序：一条命令，7 个文件，所有原子一致
EXPECTED_ORDER = [
    "core.py",
    "meta.json",
    "server.py",
    "Dockerfile",
    "requirements.txt",
    "tests/test_smoke.py",
    "tests/test_contract.py",
]

ATOM_ID = "com.example.weather-sensor"


def _invoke(args: list[str]):
    return runner.invoke(app, ["atom", "init", *args])


def test_atom_files_template_order_is_fixed():
    """模板清单本身必须保持 §7 固定排序。"""
    assert [rel for rel, _ in ATOM_FILES] == EXPECTED_ORDER


def test_atom_init_creates_seven_files_in_fixed_order(tmp_path):
    result = _invoke([ATOM_ID, "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output

    target = tmp_path / ATOM_ID
    generated = sorted(
        p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()
    )
    assert generated == sorted(EXPECTED_ORDER)
    # 目录层级与 §7 一致：tests/ 下恰好两个用例文件
    assert (target / "tests").is_dir()


def test_atom_init_meta_json_contract(tmp_path):
    """meta.json：可解析、含空白 I/O schema、side_effect 默认 impure。"""
    result = _invoke([ATOM_ID, "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output

    meta = json.loads((tmp_path / ATOM_ID / "meta.json").read_text(encoding="utf-8"))
    assert meta["id"] == ATOM_ID
    assert meta["side_effect"] == "impure"
    assert meta["input"]["type"] == "json"
    assert meta["output"]["type"] == "json"

    # 内嵌空白 schema 必须是合法 JSON Schema
    jsonschema = pytest.importorskip("jsonschema")
    for direction in ("input", "output"):
        schema = meta[direction]["schema"]
        jsonschema.validators.validator_for(schema).check_schema(schema)


def test_atom_init_server_defaults_to_loopback(tmp_path):
    """server.py 加固骨架：默认 127.0.0.1、5MB 上限、YUANZI_TOKEN 鉴权。"""
    result = _invoke([ATOM_ID, "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output

    server_py = (tmp_path / ATOM_ID / "server.py").read_text(encoding="utf-8")
    assert 'os.environ.get("HOST", "127.0.0.1")' in server_py
    assert "5 * 1024 * 1024" in server_py
    assert "YUANZI_TOKEN" in server_py


def test_atom_init_generated_project_pytest_passes(tmp_path):
    """生成物开箱即用：在其目录内跑 pytest 必须全绿。"""
    result = _invoke([ATOM_ID, "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output

    target = tmp_path / ATOM_ID
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q"],
        cwd=target,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "failed" not in proc.stdout


def test_atom_init_existing_directory_friendly_error(tmp_path):
    args = [ATOM_ID, "-o", str(tmp_path)]
    first = _invoke(args)
    assert first.exit_code == 0, first.output

    second = _invoke(args)
    assert second.exit_code == 1
    assert "already exists" in second.output
    assert "Traceback" not in second.output


def test_atom_init_rejects_invalid_atom_id(tmp_path):
    result = _invoke(["BAD ID!!", "-o", str(tmp_path)])
    assert result.exit_code == 1
    assert "invalid atom id" in result.output
    assert not (tmp_path / "BAD ID!!").exists()


def test_atom_init_rejects_non_reverse_domain_id(tmp_path):
    """单词名（非反向域名）同样拒绝，与 meta.py 校验一致。"""
    result = _invoke(["weather-sensor", "-o", str(tmp_path)])
    assert result.exit_code == 1
    assert "invalid atom id" in result.output
    assert not (tmp_path / "weather-sensor").exists()


def test_legacy_init_command_still_listed():
    """既有 `yuanzi init` 兼容保留，帮助中仍可见。"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "atom" in result.output
