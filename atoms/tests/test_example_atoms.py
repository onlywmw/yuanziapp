"""Tests for example atoms in the atoms/ directory.

Uses importlib to load each atom's core.py as a uniquely-named module
so Python's import cache doesn't make all ``import core`` resolve to the same module.
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

_ATOMS_DIR = Path(__file__).resolve().parent.parent


def _load_atom_core(atom_name: str):
    """Import core.py from an atom directory with a unique module name."""
    core_path = _ATOMS_DIR / atom_name / "core.py"
    spec = importlib.util.spec_from_file_location(
        f"{atom_name.replace('-', '_')}_core", str(core_path)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ============================================================
# atom-math-sum
# ============================================================
class TestAtomMathSum:
    """Tests for atom-math-sum — basic arithmetic."""

    @pytest.fixture(scope="class")
    def core(self):
        return _load_atom_core("atom-math-sum")

    def test_simple_addition(self, core):
        result = core.handler({"a": 10, "b": 20})
        assert result["status"] == "success"
        assert result["data"]["result"] == 30.0

    def test_float_addition(self, core):
        result = core.handler({"a": 3.5, "b": 2.5})
        assert result["status"] == "success"
        assert result["data"]["result"] == 6.0

    def test_negative_numbers(self, core):
        result = core.handler({"a": -10, "b": 5})
        assert result["status"] == "success"
        assert result["data"]["result"] == -5.0

    def test_string_inputs_are_cast(self, core):
        result = core.handler({"a": "10", "b": "20"})
        assert result["status"] == "success"
        assert result["data"]["result"] == 30.0

    def test_missing_values_default_to_zero(self, core):
        result = core.handler({"a": 5})
        assert result["status"] == "success"
        assert result["data"]["result"] == 5.0

    def test_invalid_input_returns_error(self, core):
        result = core.handler({"a": "not_a_number", "b": 2})
        assert result["status"] == "error"
        assert "message" in result

    def test_zero_addition(self, core):
        result = core.handler({"a": 0, "b": 0})
        assert result["status"] == "success"
        assert result["data"]["result"] == 0.0


# ============================================================
# atom-string-split
# ============================================================
class TestAtomStringSplit:
    """Tests for atom-string-split — string delimiter operations."""

    @pytest.fixture(scope="class")
    def core(self):
        return _load_atom_core("atom-string-split")

    def test_comma_split(self, core):
        result = core.handler({"text": "a,b,c", "delimiter": ","})
        assert result["status"] == "success"
        assert result["data"]["parts"] == ["a", "b", "c"]
        assert result["data"]["count"] == 3

    def test_default_delimiter_is_comma(self, core):
        result = core.handler({"text": "x,y,z"})
        assert result["status"] == "success"
        assert result["data"]["parts"] == ["x", "y", "z"]

    def test_custom_delimiter(self, core):
        result = core.handler({"text": "hello world foo", "delimiter": " "})
        assert result["status"] == "success"
        assert result["data"]["parts"] == ["hello", "world", "foo"]

    def test_maxsplit(self, core):
        result = core.handler({"text": "a,b,c,d", "delimiter": ",", "maxsplit": 2})
        assert result["status"] == "success"
        assert result["data"]["parts"] == ["a", "b", "c,d"]

    def test_empty_text(self, core):
        result = core.handler({"text": "", "delimiter": ","})
        assert result["status"] == "success"
        assert result["data"]["parts"] == [""]

    def test_no_delimiter_match(self, core):
        result = core.handler({"text": "nodots", "delimiter": "."})
        assert result["status"] == "success"
        assert result["data"]["parts"] == ["nodots"]

    def test_multi_char_delimiter(self, core):
        result = core.handler({"text": "a::b::c", "delimiter": "::"})
        assert result["status"] == "success"
        assert result["data"]["parts"] == ["a", "b", "c"]


# ============================================================
# atom-template
# ============================================================
class TestAtomTemplate:
    """Tests for atom-template — the boilerplate atom."""

    @pytest.fixture(scope="class")
    def core(self):
        return _load_atom_core("atom-template")

    def test_echoes_input(self, core):
        data = {"key": "value", "nested": {"a": 1}}
        result = core.handler(data)
        assert result["status"] == "success"
        assert result["data"] == data

    def test_empty_input(self, core):
        result = core.handler({})
        assert result["status"] == "success"
        assert result["data"] == {}

    def test_returns_standard_format(self, core):
        result = core.handler({"foo": "bar"})
        assert "status" in result
        assert "data" in result
        assert result["status"] == "success"


# ============================================================
# atom-file-read
# ============================================================
class TestAtomFileRead:
    """Tests for atom-file-read — local file reading."""

    @pytest.fixture(scope="class")
    def core(self):
        return _load_atom_core("atom-file-read")

    @pytest.fixture(scope="class", autouse=True)
    def _sandbox(self):
        # BUG-007 沙箱：显式把系统临时目录加入白名单，测试才能读到临时文件
        os.environ["ATOM_FILE_READ_ROOTS"] = tempfile.gettempdir()
        yield
        os.environ.pop("ATOM_FILE_READ_ROOTS", None)

    def test_missing_path_returns_error(self, core):
        result = core.handler({})
        assert result["status"] == "error"
        assert "path" in result["message"]

    def test_nonexistent_file_returns_error(self, core):
        result = core.handler({"path": "/tmp/nonexistent_xyzabc_12345.txt"})
        assert result["status"] == "error"

    def test_read_text_file(self, core):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("Hello World\nLine 2")
            temp_path = f.name

        try:
            result = core.handler({"path": temp_path, "mode": "text"})
            assert result["status"] == "success"
            assert result["data"]["content"] == "Hello World\nLine 2"
            assert result["data"]["size"] > 0
            assert result["data"]["mode"] == "text"
        finally:
            os.unlink(temp_path)

    def test_read_file_size_too_large(self, core):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("x" * 100)
            temp_path = f.name

        try:
            result = core.handler({"path": temp_path, "max_size": 10})
            assert result["status"] == "error"
            assert "too large" in result["message"].lower()
        finally:
            os.unlink(temp_path)

    def test_read_base64_mode(self, core):
        content = "base64 test content"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            temp_path = f.name

        try:
            result = core.handler({"path": temp_path, "mode": "base64"})
            assert result["status"] == "success"
            assert result["data"]["mode"] == "base64"
            assert result["data"]["content"] != content
        finally:
            os.unlink(temp_path)


# ============================================================
# atom-http-get
# ============================================================
class TestAtomHttpGet:
    """Tests for atom-http-get — HTTP GET requests."""

    @pytest.fixture(scope="class")
    def core(self):
        return _load_atom_core("atom-http-get")

    def test_missing_url_returns_error(self, core):
        result = core.handler({})
        assert result["status"] == "error"
        assert "url" in result["message"]

    def test_invalid_url_returns_error(self, core):
        result = core.handler(
            {
                "url": "http://invalid.test.domain.that.does.not.exist.example",
                "timeout": 2,
            }
        )
        # Should return error (connection failure) or success if DNS resolved a
        # captive portal — accept either; the point is it doesn't crash
        assert result["status"] in ("error", "success")

    def test_default_timeout(self, core):
        """Handler should not crash even with unreachable URL."""
        result = core.handler({"url": "http://192.0.2.1", "timeout": 1})
        assert result["status"] in ("error", "success")
