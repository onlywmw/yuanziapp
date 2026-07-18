#!/usr/bin/env python3
"""Push Yuanzi project files to an Android tablet via adb.

Reads ``yuanzi-config.yaml`` for the adb path, device root, ignore patterns and
sync items.  Files are first staged into a temporary directory (ignoring
unwanted patterns) and then pushed with ``adb push``.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

DEFAULT_CONFIG = "yuanzi-config.yaml"


def load_config(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _expand_env(raw)


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def should_ignore(rel: Path, patterns: list[str]) -> bool:
    """Return True if *rel* matches any ignore pattern.

    Patterns are matched against both the full relative POSIX path and each
    path component, similar to ``.gitignore`` light-weight behavior.
    """
    posix = rel.as_posix()
    parts = rel.parts
    for pattern in patterns:
        # Full path match (e.g. "a/b/c.py")
        if fnmatch.fnmatch(posix, pattern):
            return True
        # Basename match (e.g. "*.pyc" or "__pycache__")
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def stage_item(
    src: Path,
    dst: PurePosixPath,
    staging: Path,
    ignore_patterns: list[str],
) -> None:
    """Copy *src* into *staging* under *dst*, respecting ignore patterns."""
    target = staging / dst.as_posix().lstrip("/")
    if src.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        return

    if not src.is_dir():
        raise FileNotFoundError(f"Sync source not found: {src}")

    for root, dirs, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        # Filter out ignored directories in-place so os.walk does not descend.
        kept_dirs = []
        for d in dirs:
            rel = rel_root / d if rel_root.name or rel_root.parts else Path(d)
            if should_ignore(rel, ignore_patterns):
                print(f"  ignore dir  {rel}")
            else:
                kept_dirs.append(d)
        dirs[:] = kept_dirs

        for f in files:
            rel = rel_root / f if rel_root.name or rel_root.parts else Path(f)
            if should_ignore(rel, ignore_patterns):
                print(f"  ignore file {rel}")
                continue
            src_file = Path(root) / f
            dst_file = target / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)


def run_cmd(cmd: list[str], dry_run: bool = False) -> int:
    """Run a command and return its exit code."""
    print(f"$ {' '.join(cmd)}")
    if dry_run:
        return 0
    result = subprocess.run(cmd)
    return result.returncode


def adb_check(adb: str) -> bool:
    result = subprocess.run([adb, "devices"], capture_output=True, text=True)
    if result.returncode != 0:
        print("adb devices failed:", result.stderr, file=sys.stderr)
        return False
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    # First line is header, subsequent lines are devices.
    devices = [line for line in lines[1:] if line.endswith("device")]
    if not devices:
        print("No adb device connected:", result.stdout, file=sys.stderr)
        return False
    for d in devices:
        print(f"  device: {d}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync Yuanzi project to Android tablet"
    )
    parser.add_argument(
        "-c", "--config", default=DEFAULT_CONFIG, help="Path to yuanzi-config.yaml"
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="Show what would be done"
    )
    parser.add_argument("--no-chown", action="store_true", help="Skip chown on device")
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    config = load_config(config_path)
    sync_cfg = config.get("sync", {})
    adb = sync_cfg.get("adb_path", "adb")
    device_root = sync_cfg.get(
        "device_root", "/data/data/com.termux/files/home/yuanzi-project"
    )
    device_user = sync_cfg.get("device_user", "u0_a304")
    ignore_patterns = sync_cfg.get("ignore", [])
    items = sync_cfg.get("items", [])

    if not items:
        print("No sync items configured.", file=sys.stderr)
        return 1

    project_root = config_path.parent

    print(f"Config:    {config_path}")
    print(f"adb:       {adb}")
    print(f"Device:    {device_root}")
    print(f"Dry run:   {args.dry_run}")
    print()

    if not adb_check(adb):
        return 1

    with tempfile.TemporaryDirectory(prefix="yuanzi-sync-") as tmp:
        staging = Path(tmp) / "staging"
        staging.mkdir()

        for item in items:
            src_rel = item["src"]
            dst_rel = item["dst"]
            src = project_root / src_rel
            dst = PurePosixPath(device_root) / dst_rel
            print(f"Staging {src_rel} -> {dst}")
            try:
                stage_item(src, PurePosixPath("/") / dst_rel, staging, ignore_patterns)
            except FileNotFoundError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        # Push the whole staging tree to the device root.
        push_cmd = [adb, "push", f"{staging}/.", f"{device_root}/"]
        rc = run_cmd(push_cmd, dry_run=args.dry_run)
        if rc != 0:
            return rc

        if not args.no_chown and not args.dry_run:
            chown_cmd = [
                adb,
                "shell",
                "su",
                "-c",
                f"'chown -R {device_user}:{device_user} {device_root}'",
            ]
            # On Windows the outer shell may strip quotes; pass as a single adb shell argument.
            chown_cmd = [
                adb,
                "shell",
                f"su -c 'chown -R {device_user}:{device_user} {device_root}'",
            ]
            rc = run_cmd(chown_cmd, dry_run=args.dry_run)
            if rc != 0:
                print(
                    "chown failed; files are pushed but ownership may be wrong.",
                    file=sys.stderr,
                )
                return rc

    print("Sync complete.")
    if not args.dry_run:
        print(
            f"Restart Yuanzi on the tablet with: sh {device_root}/start_yuanzi_termux.sh"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
