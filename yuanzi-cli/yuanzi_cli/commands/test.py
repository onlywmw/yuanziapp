"""`yuanzi test` command - run tests for an atom."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from yuanzi_cli.commands.validate import run_validate

app = typer.Typer()


def run_test(
    path: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Path to the atom directory",
    ),
    validate: bool = typer.Option(
        True,
        "--validate/--no-validate",
        help="Run yuanzi validate before executing tests",
    ),
    fast: bool = typer.Option(
        False,
        "--fast",
        help="Run only fast kernel tests (skip server/endpoint tests)",
    ),
    pytest_args: list[str] = typer.Argument(
        [],
        help="Additional arguments forwarded to pytest",
    ),
) -> None:
    """Run pytest for a Yuanzi atom.

    By default the atom is validated first; use --no-validate to skip.
    Use --fast to run only kernel-level tests and skip endpoint tests.
    """
    atom_dir = path.resolve()

    if validate:
        run_validate(atom_dir)
        typer.echo("---")

    extra_args = ["-k", "kernel"] if fast else []
    typer.echo(f"Running pytest in {atom_dir}" + (" (fast mode)" if fast else ""))
    cmd = [sys.executable, "-m", "pytest", str(atom_dir), *extra_args, *pytest_args]
    result = subprocess.run(cmd, cwd=atom_dir)
    raise typer.Exit(code=result.returncode)
