"""Tests for the yuanzi validate command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner
from yuanzi_cli.main import app

runner = CliRunner()

EXAMPLE_SUM = (
    Path(__file__).resolve().parents[2]
    / "yuanzi-atom-templates"
    / "examples"
    / "com.example.sum"
)


def test_validate_example_sum():
    result = runner.invoke(app, ["validate", str(EXAMPLE_SUM)])
    assert result.exit_code == 0, result.output
    assert "com.example.sum@0.1.0" in result.output


def test_validate_missing_meta(tmp_path):
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 1
    assert "meta.yaml not found" in result.output


def test_validate_invalid_meta(tmp_path):
    meta = tmp_path / "meta.yaml"
    meta.write_text("id: bad-id\nversion: 0.1\n")
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 1
    assert "validation failed" in result.output


VALID_META = """\
id: com.example.mini
version: 0.1.0
name: Mini
description: minimal atom
type: skill
kernel_type: python_script
author: test
license: MIT
runtime:
  interface: std-atom-http-v1
  port: 18000
"""


def _make_atom(tmp_path, kernel_test: str) -> Path:
    (tmp_path / "meta.yaml").write_text(VALID_META)
    (tmp_path / "server.py").write_text("# server\n")
    atom = tmp_path / "atom"
    atom.mkdir()
    (atom / "__init__.py").write_text("")
    (atom / "core.py").write_text("def handle(payload):\n    return payload\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_kernel.py").write_text(kernel_test)
    (tests / "test_health.py").write_text("# health tests\n")
    return tmp_path


def test_validate_kernel_test_must_stay_offline(tmp_path):
    atom = _make_atom(tmp_path, "import requests\nfrom atom.core import handle\n")
    result = runner.invoke(app, ["validate", str(atom)])
    assert result.exit_code == 1
    assert "must stay offline" in result.output
    assert "import requests" in result.output


def test_validate_clean_kernel_test_passes(tmp_path):
    atom = _make_atom(tmp_path, "import pytest\nfrom atom.core import handle\n")
    result = runner.invoke(app, ["validate", str(atom)])
    assert result.exit_code == 0, result.output
