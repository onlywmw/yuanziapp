"""Ensure atoms/tests can be collected by pytest when run together with other
test directories that have their own pyproject.toml (e.g. yuanzi-cli).

Without this, Python's import system may resolve ``tests`` to the wrong
directory when multiple ``tests/`` dirs exist in the same session.
"""

import sys
from pathlib import Path

# Make sure the atoms/ directory is importable
_atoms_root = Path(__file__).resolve().parent.parent
if str(_atoms_root) not in sys.path:
    sys.path.insert(0, str(_atoms_root))
