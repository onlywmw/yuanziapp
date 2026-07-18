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
    pytest_args: list[str] = typer.Argument(
        [],
        help="Additional arguments forwarded to pytest",
    ),
) -> None:
    """Run pytest for a Yuanzi atom.

    By default the atom is validated first; use --no-validate to skip.
    """
    atom_dir = path.resolve()

    if validate:
        run_validate(atom_dir)
        typer.echo("---")

    typer.echo(f"Running pytest in {atom_dir}")
    cmd = [sys.executable, "-m", "pytest", str(atom_dir), *pytest_args]
    result = subprocess.run(cmd, cwd=atom_dir)
    raise typer.Exit(code=result.returncode)
