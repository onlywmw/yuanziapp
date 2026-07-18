"""Kernel unit tests."""
import pytest

from atom.core import handle


def test_handle_returns_dict():
    result = handle({"message": "hello"})
    assert isinstance(result, dict)


def test_handle_echoes_input():
    result = handle({"message": "hello"})
    assert result == {"echo": {"message": "hello"}}
