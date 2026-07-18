"""`yuanzi init` command - scaffold a new atom from a Cookiecutter template."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from cookiecutter.main import cookiecutter

from yuanzi_cli.templates import default_template_dir

app = typer.Typer()


def run_init(
    atom_id: Optional[str] = typer.Argument(
        None, help="Reverse-domain atom id (e.g. com.example.my-atom)"
    ),
    template_dir: Optional[Path] = typer.Option(
        None,
        "--template-dir",
        "-t",
        help="Path to the atom Cookiecutter template directory",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    output_dir: Path = typer.Option(
        Path("."),
        "--output-dir",
        "-o",
        help="Directory where the new atom folder will be created",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
) -> None:
    """Create a new Yuanzi atom from the official template."""
    template = template_dir or default_template_dir()
    extra_context: dict[str, str] = {}
    no_input = False

    if atom_id:
        extra_context["atom_id"] = atom_id
        no_input = True
        typer.echo(f"Scaffolding atom '{atom_id}' from {template}")
    else:
        typer.echo(f"Scaffolding a new atom from {template}")

    result = cookiecutter(
        str(template),
        output_dir=str(output_dir),
        extra_context=extra_context,
        no_input=no_input,
    )
    typer.echo(f"Created atom at: {result}")
