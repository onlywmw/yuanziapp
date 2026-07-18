"""`yuanzi install-hooks` command - install pre-commit hooks for the repo."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer()


def _find_repo_root(start: Path) -> Path | None:
    """Walk upwards from `start` looking for .pre-commit-config.yaml."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".pre-commit-config.yaml").exists():
            return candidate
    return None


def _run(cmd: list[str], cwd: Path) -> int:
    typer.echo(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd).returncode


def run_install_hooks(
    path: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Directory to start searching for the repository root",
    ),
) -> None:
    """Install pre-commit and register the repository's git hooks.

    Searches upwards from PATH for .pre-commit-config.yaml, installs the
    pre-commit package if needed, then runs `pre-commit install`.
    """
    repo_root = _find_repo_root(path)
    if repo_root is None:
        typer.echo(
            f"Error: no .pre-commit-config.yaml found in {path.resolve()} "
            "or any parent directory",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Repository root: {repo_root}")

    rc = _run(
        [sys.executable, "-m", "pip", "install", "pre-commit", "-q"], cwd=repo_root
    )
    if rc != 0:
        typer.echo("Error: failed to install pre-commit", err=True)
        raise typer.Exit(code=rc)

    rc = _run(
        [
            sys.executable,
            "-m",
            "pre_commit",
            "install",
            "--config",
            str(repo_root / ".pre-commit-config.yaml"),
        ],
        cwd=repo_root,
    )
    if rc != 0:
        typer.echo("Error: pre-commit install failed", err=True)
        raise typer.Exit(code=rc)

    typer.echo("Hooks installed. They will run automatically on 'git commit'.")
    typer.echo("To run them manually: pre-commit run --all-files")
