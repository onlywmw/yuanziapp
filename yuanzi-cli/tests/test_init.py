"""Tests for the yuanzi init command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner
from yuanzi_cli.main import app

runner = CliRunner()


def test_init_creates_atom(tmp_path):
    template_dir = Path(__file__).resolve().parents[2] / "yuanzi-atom-templates"
    result = runner.invoke(
        app,
        [
            "init",
            "com.example.test-atom",
            "--template-dir",
            str(template_dir),
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    expected = tmp_path / "com.example.test-atom"
    assert expected.exists()
    assert (expected / "meta.yaml").exists()
    assert (expected / "server.py").exists()
    assert (expected / "atom" / "core.py").exists()


def test_init_rejects_invalid_atom_id(tmp_path):
    template_dir = Path(__file__).resolve().parents[2] / "yuanzi-atom-templates"
    result = runner.invoke(
        app,
        [
            "init",
            "BAD ID!!",
            "--template-dir",
            str(template_dir),
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "invalid atom id" in result.output
    assert not (tmp_path / "BAD ID!!").exists()


def test_init_existing_directory_friendly_error(tmp_path):
    template_dir = Path(__file__).resolve().parents[2] / "yuanzi-atom-templates"
    args = [
        "init",
        "com.qa.dup",
        "--template-dir",
        str(template_dir),
        "--output-dir",
        str(tmp_path),
    ]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output

    second = runner.invoke(app, args)
    assert second.exit_code == 1
    assert "already exists" in second.output
    assert "Traceback" not in second.output
