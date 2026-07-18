"""Sum atom kernel.

The `handle` function receives a JSON payload and returns the sum of `a` and `b`.
"""

from typing import Any, Dict


def handle(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the sum of two numbers.

    Args:
        payload: Must contain numeric fields `a` and `b`.

    Returns:
        {"result": a + b}
    """
    a = payload.get("a", 0)
    b = payload.get("b", 0)
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise ValueError("a and b must be numbers")
    return {"result": a + b}
