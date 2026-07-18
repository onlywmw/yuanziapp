"""Helpers for locating the atom template directory."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_TEMPLATE_DIR_NAME = "yuanzi-atom-templates"


def default_template_dir() -> Path:
    """Return the default atom template directory.

    Resolution order:
    1. ``YUANZI_TEMPLATES_DIR`` environment variable.
    2. Sibling directory ``yuanzi-atom-templates`` next to the repository root.
    3. Bundled template directory inside the package (for wheel installs).
    """
    env_dir = os.environ.get("YUANZI_TEMPLATES_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    # Running from a checkout: yuanzi-cli/ is a sibling of yuanzi-atom-templates/.
    checkout_candidate = Path(__file__).resolve().parents[2] / DEFAULT_TEMPLATE_DIR_NAME
    if checkout_candidate.exists():
        return checkout_candidate

    # Fallback: bundled template shipped with the wheel.
    bundled = Path(__file__).with_name("templates") / DEFAULT_TEMPLATE_DIR_NAME
    if bundled.exists():
        return bundled

    raise FileNotFoundError(
        f"Could not find atom template directory. "
        f"Set YUANZI_TEMPLATES_DIR or ensure {DEFAULT_TEMPLATE_DIR_NAME} exists."
    )
