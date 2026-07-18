"""Kernel unit tests for com.example.sum."""

import pytest
from atom.core import handle


def test_sum_integers():
    assert handle({"a": 1, "b": 2}) == {"result": 3}


def test_sum_floats():
    assert handle({"a": 1.5, "b": 2.5}) == {"result": 4.0}


def test_sum_defaults_to_zero():
    assert handle({}) == {"result": 0}


def test_sum_with_only_a():
    assert handle({"a": 7}) == {"result": 7}


def test_sum_invalid_input_raises():
    with pytest.raises(ValueError):
        handle({"a": "x", "b": 2})
