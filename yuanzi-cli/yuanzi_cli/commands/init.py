"""`yuanzi init` command - scaffold a new atom from a Cookiecutter template."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from cookiecutter.exceptions import CookiecutterException, OutputDirExistsException
from cookiecutter.main import cookiecutter

from yuanzi_cli.meta import atom_id_error
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
    if atom_id:
        error = atom_id_error(atom_id)
        if error:
            typer.echo(f"Error: invalid atom id: {error}", err=True)
            raise typer.Exit(code=1)

    template = template_dir or default_template_dir()
    extra_context: dict[str, str] = {}
    no_input = False

    if atom_id:
        extra_context["atom_id"] = atom_id
        no_input = True
        typer.echo(f"Scaffolding atom '{atom_id}' from {template}")
    else:
        typer.echo(f"Scaffolding a new atom from {template}")

    try:
        result = cookiecutter(
            str(template),
            output_dir=str(output_dir),
            extra_context=extra_context,
            no_input=no_input,
        )
    except OutputDirExistsException:
        typer.echo(
            f"Error: output directory for '{atom_id}' already exists in "
            f"{output_dir.resolve()}",
            err=True,
        )
        raise typer.Exit(code=1)
    except CookiecutterException as exc:
        typer.echo(f"Error: failed to scaffold atom: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Created atom at: {result}")
