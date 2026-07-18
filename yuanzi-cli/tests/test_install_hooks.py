"""Tests for the yuanzi install-hooks command."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from typer.testing import CliRunner
from yuanzi_cli.commands import install_hooks
from yuanzi_cli.main import app

runner = CliRunner()

PIP_CMD = (sys.executable, "-m", "pip", "install", "pre-commit", "-q")


def _config(tmp_path):
    config = tmp_path / ".pre-commit-config.yaml"
    config.write_text("repos: []\n")
    return config


def _install_cmd(config):
    return (
        sys.executable,
        "-m",
        "pre_commit",
        "install",
        "--config",
        str(config),
    )


def _stub_run(monkeypatch, returncodes):
    """Stub subprocess.run; returncodes maps a command-key tuple to its rc."""
    calls = []

    def fake_run(cmd, cwd=None):
        calls.append((tuple(cmd), cwd))
        for key, rc in returncodes.items():
            if tuple(cmd)[: len(key)] == key:
                return SimpleNamespace(returncode=rc)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(install_hooks.subprocess, "run", fake_run)
    return calls


def test_install_hooks_no_config(tmp_path, monkeypatch):
    # 与文件系统环境无关：直接模拟"向上找不到配置"
    monkeypatch.setattr(install_hooks, "_find_repo_root", lambda path: None)
    result = runner.invoke(app, ["install-hooks", str(tmp_path)])
    assert result.exit_code == 1
    assert "no .pre-commit-config.yaml found" in result.output


def test_install_hooks_success(tmp_path, monkeypatch):
    config = _config(tmp_path)
    calls = _stub_run(monkeypatch, {})

    result = runner.invoke(app, ["install-hooks", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Hooks installed" in result.output
    assert [c[0] for c in calls] == [PIP_CMD, _install_cmd(config)]
    assert all(c[1] == tmp_path for c in calls)


def test_install_hooks_finds_root_in_parents(tmp_path, monkeypatch):
    config = _config(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    calls = _stub_run(monkeypatch, {})

    result = runner.invoke(app, ["install-hooks", str(nested)])
    assert result.exit_code == 0, result.output
    assert [c[0] for c in calls] == [PIP_CMD, _install_cmd(config)]


def test_install_hooks_pip_failure(tmp_path, monkeypatch):
    _config(tmp_path)
    _stub_run(monkeypatch, {PIP_CMD: 1})

    result = runner.invoke(app, ["install-hooks", str(tmp_path)])
    assert result.exit_code == 1
    assert "failed to install pre-commit" in result.output


def test_install_hooks_install_failure(tmp_path, monkeypatch):
    _config(tmp_path)
    _stub_run(monkeypatch, {(sys.executable, "-m", "pre_commit"): 2})

    result = runner.invoke(app, ["install-hooks", str(tmp_path)])
    assert result.exit_code == 2
    assert "pre-commit install failed" in result.output
