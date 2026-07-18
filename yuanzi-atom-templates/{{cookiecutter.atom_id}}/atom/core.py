"""Atom kernel: implement your business logic here.

The `handle` function receives a JSON payload from the `/run` endpoint
and must return a JSON-serializable dict.
"""
from typing import Any, Dict


def handle(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle a single invocation.

    Args:
        payload: The request body parsed as JSON.

    Returns:
        A JSON-serializable response dict.
    """
    # TODO: replace with real logic
    return {"echo": payload}
