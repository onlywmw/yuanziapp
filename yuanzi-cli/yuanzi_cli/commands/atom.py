"""`yuanzi atom` 命令组 - 原子脚手架（v2.1 §7 固定 7 文件布局）。"""

from __future__ import annotations

from pathlib import Path

import typer

from yuanzi_cli.atom_templates import ATOM_FILES
from yuanzi_cli.meta import atom_id_error

app = typer.Typer(help="原子脚手架（v2.1 §7）", no_args_is_help=True)


def scaffold_atom(atom_id: str, output_dir: Path) -> Path:
    """按固定排序生成 7 个文件，返回原子目录。

    目录已存在时抛 FileExistsError，由调用方转成友好错误（BUG-002）。
    """
    target = Path(output_dir) / atom_id
    if target.exists():
        raise FileExistsError(f"output directory '{target}' already exists")
    name = atom_id.split(".")[-1]
    for rel_path, template in ATOM_FILES:
        content = template.replace("__ATOM_ID__", atom_id).replace(
            "__ATOM_NAME__", name
        )
        dest = target / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="\n")
    return target


@app.command(name="init")
def atom_init(
    atom_id: str = typer.Argument(
        ..., help="反向域名风格 atom id（如 com.example.weather-sensor）"
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
    """Scaffold a new atom: 7 files in fixed order (core/meta/server/...)."""
    # 复用 meta.py 既有校验（BUG-001）：非法 id 直接拒绝，不生成目录
    error = atom_id_error(atom_id)
    if error:
        typer.echo(f"Error: invalid atom id: {error}", err=True)
        raise typer.Exit(code=1)

    try:
        result = scaffold_atom(atom_id, output_dir)
    except FileExistsError:
        typer.echo(
            f"Error: output directory for '{atom_id}' already exists in "
            f"{output_dir.resolve()}",
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo(f"Created atom at: {result}")
    for rel_path, _ in ATOM_FILES:
        typer.echo(f"  {rel_path}")
