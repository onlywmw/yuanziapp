"""`yuanzi validate` command - validate an atom directory."""

from __future__ import annotations

import re
from pathlib import Path

import typer
from pydantic import ValidationError

from yuanzi_cli.meta import load_meta, validate_meta

app = typer.Typer()


REQUIRED_FILES = {
    "python_script": [
        "meta.yaml",
        "server.py",
        Path("atom") / "__init__.py",
        Path("atom") / "core.py",
        Path("tests") / "test_kernel.py",
        Path("tests") / "test_health.py",
    ],
    "markdown_rules": [
        "meta.yaml",
        "rules.md",
    ],
    "prompt_txt": [
        "meta.yaml",
        "prompt.txt",
    ],
}

# 冒烟测试规范（docs/atom-smoke-test-spec.md §3）：内核冒烟必须离线，
# 不允许 import server / 网络相关模块。
KERNEL_TEST_FORBIDDEN_IMPORTS = (
    "server",
    "requests",
    "urllib",
    "http",
    "socket",
)


def _missing_files(atom_dir: Path, kernel_type: str) -> list[str]:
    expected = REQUIRED_FILES.get(kernel_type, [])
    missing: list[str] = []
    for item in expected:
        rel = item if isinstance(item, str) else item.as_posix()
        if not (atom_dir / rel).exists():
            missing.append(rel)
    return missing


_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][\w]*)")


def _kernel_test_forbidden_imports(atom_dir: Path) -> list[str]:
    """Return forbidden imports found in tests/test_kernel.py."""
    test_file = atom_dir / "tests" / "test_kernel.py"
    if not test_file.exists():
        return []
    found: list[str] = []
    for line in test_file.read_text(encoding="utf-8").splitlines():
        match = _IMPORT_RE.match(line)
        if match and match.group(1) in KERNEL_TEST_FORBIDDEN_IMPORTS:
            found.append(line.strip())
    return found


def run_validate(
    path: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Path to the atom directory",
    ),
) -> None:
    """Validate meta.yaml and directory structure of a Yuanzi atom."""
    atom_dir = path.resolve()
    meta_path = atom_dir / "meta.yaml"

    if not meta_path.exists():
        typer.echo(f"Error: meta.yaml not found in {atom_dir}", err=True)
        raise typer.Exit(code=1)

    try:
        raw = load_meta(str(meta_path))
    except Exception as exc:
        typer.echo(f"Error: failed to parse meta.yaml: {exc}", err=True)
        raise typer.Exit(code=1)

    try:
        meta = validate_meta(raw)
    except ValidationError as exc:
        typer.echo("Error: meta.yaml validation failed", err=True)
        for error in exc.errors():
            loc = ".".join(str(x) for x in error["loc"])
            typer.echo(f"  - {loc}: {error['msg']}", err=True)
        raise typer.Exit(code=1)

    missing = _missing_files(atom_dir, meta.kernel_type)
    if missing:
        typer.echo(
            f"Error: missing required files for kernel_type '{meta.kernel_type}'",
            err=True,
        )
        for name in missing:
            typer.echo(f"  - {name}", err=True)
        raise typer.Exit(code=1)

    if meta.kernel_type == "python_script":
        forbidden = _kernel_test_forbidden_imports(atom_dir)
        if forbidden:
            typer.echo(
                "Error: tests/test_kernel.py must stay offline "
                "(see docs/atom-smoke-test-spec.md); forbidden imports:",
                err=True,
            )
            for line in forbidden:
                typer.echo(f"  - {line}", err=True)
            raise typer.Exit(code=1)

    typer.echo(f"OK: {meta.id}@{meta.version} is a valid Yuanzi atom")
