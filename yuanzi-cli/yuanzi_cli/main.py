"""Yuanzi CLI entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from yuanzi_cli import __version__
from yuanzi_cli.commands.init import run_init
from yuanzi_cli.commands.install_hooks import run_install_hooks
from yuanzi_cli.commands.test import run_test
from yuanzi_cli.commands.validate import run_validate

app = typer.Typer(
    name="yuanzi",
    help="CLI for the Yuanzi atom ecosystem",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"yuanzi-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """Yuanzi atom developer tools."""


@app.command()
def init(
    atom_id: Optional[str] = typer.Argument(None, help="Reverse-domain atom id"),
    template_dir: Optional[Path] = typer.Option(
        None, "--template-dir", "-t", help="Path to Cookiecutter template"
    ),
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-o", help="Output directory"
    ),
) -> None:
    """Scaffold a new atom from the official template."""
    run_init(atom_id, template_dir, output_dir)


@app.command()
def validate(
    path: Path = typer.Argument(Path("."), help="Path to atom directory"),
) -> None:
    """Validate an atom's meta.yaml and directory structure."""
    run_validate(path)


@app.command()
def test(
    path: Path = typer.Argument(Path("."), help="Path to atom directory"),
    validate_first: bool = typer.Option(
        True, "--validate/--no-validate", help="Validate atom before running tests"
    ),
    fast: bool = typer.Option(False, "--fast", help="Run only fast kernel tests"),
    pytest_args: list[str] = typer.Argument([], help="Extra pytest arguments"),
) -> None:
    """Run an atom's pytest suite."""
    run_test(path, validate_first, fast, pytest_args)


@app.command(name="install-hooks")
def install_hooks(
    path: Path = typer.Argument(
        Path("."), help="Directory to start searching for the repository root"
    ),
) -> None:
    """Install pre-commit and register the repository's git hooks."""
    run_install_hooks(path)


if __name__ == "__main__":
    app()
