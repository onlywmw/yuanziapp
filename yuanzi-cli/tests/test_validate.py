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
