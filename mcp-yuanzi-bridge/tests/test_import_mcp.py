"""Tests for import_mcp_servers utility functions."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure import_mcp_servers is importable
_bridge = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_bridge))

from import_mcp_servers import (  # noqa: E402
    extract_tools,
    read_first_paragraph,
    read_pyproject_name,
    scan_mcp_servers,
)


class TestReadFirstParagraph:
    def test_reads_basic_paragraph(self):
        content = "# Title\n\nThis is the first paragraph.\nIt continues here.\n\nSecond paragraph."
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            result = read_first_paragraph(Path(path))
            assert "This is the first paragraph." in result
        finally:
            os.unlink(path)

    def test_skips_headers(self):
        content = "# Main Title\n## Subtitle\n\nActual content here.\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            result = read_first_paragraph(Path(path))
            assert "Actual content" in result
            assert "Main Title" not in result
        finally:
            os.unlink(path)

    def test_returns_empty_for_missing_file(self):
        result = read_first_paragraph(Path("/nonexistent/path/README.md"))
        assert result == ""

    def test_truncates_at_300_chars(self):
        content = "A" * 500
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            result = read_first_paragraph(Path(path))
            assert len(result) <= 300
        finally:
            os.unlink(path)


class TestReadPyprojectName:
    def test_extracts_name(self):
        content = '[project]\nname = "my-package"\nversion = "1.0.0"'
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            result = read_pyproject_name(Path(path))
            assert result == "my-package"
        finally:
            os.unlink(path)

    def test_returns_empty_for_missing_file(self):
        result = read_pyproject_name(Path("/nonexistent/pyproject.toml"))
        assert result == ""

    def test_no_name_field_returns_empty(self):
        content = "[project]\nversion = '1.0'"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            result = read_pyproject_name(Path(path))
            assert result == ""
        finally:
            os.unlink(path)


class TestExtractTools:
    def test_extracts_simple_tool(self):
        content = "@mcp.tool()\ndef get_data():\n    pass\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            result = extract_tools(Path(path))
            assert "get_data" in result
        finally:
            os.unlink(path)

    def test_extracts_async_tool(self):
        content = "@mcp.tool()\nasync def fetch_url():\n    pass\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            result = extract_tools(Path(path))
            assert "fetch_url" in result
        finally:
            os.unlink(path)

    def test_extracts_multiple_tools(self):
        content = (
            "@mcp.tool()\ndef tool_a():\n    pass\n\n"
            "@mcp.tool()\ndef tool_b():\n    pass\n\n"
            "def not_a_tool():\n    pass\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            result = extract_tools(Path(path))
            assert sorted(result) == ["tool_a", "tool_b"]
        finally:
            os.unlink(path)

    def test_returns_empty_for_missing_file(self):
        result = extract_tools(Path("/nonexistent/server.py"))
        assert result == []

    def test_extracts_multiline_tool_decorator(self):
        content = (
            '@mcp.tool(\n    name="custom",\n    description="desc"\n)\n'
            "def my_tool():\n    pass\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name

        try:
            result = extract_tools(Path(path))
            assert "my_tool" in result
        finally:
            os.unlink(path)


class TestScanMcpServers:
    def test_scans_directories(self):
        """Create a minimal mock MCP server dir and verify scan_mcp_servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir)
            server_dir = src_dir / "test-service-mcp-server"
            server_dir.mkdir()

            readme = server_dir / "README.md"
            readme.write_text("# Test\n\nDoes testing.\n", encoding="utf-8")

            server_py = server_dir / "server.py"
            server_py.write_text(
                "@mcp.tool()\ndef run_test():\n    pass\n", encoding="utf-8"
            )

            atoms = scan_mcp_servers(src_dir)
            assert len(atoms) == 1
            assert atoms[0]["atom_id"] == "mcp.test-service"
            assert atoms[0]["atom_type"] == "mcp-server"
            assert atoms[0]["status"] == "declared"
            assert "mcp/test-service/run_test" in atoms[0]["capabilities"]

    def test_skips_non_mcp_dirs(self):
        """Directories without '-mcp-server' in the name are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir)
            (src_dir / "some-other-dir").mkdir()
            (src_dir / "not-mcp").mkdir()

            atoms = scan_mcp_servers(src_dir)
            assert len(atoms) == 0

    def test_fallback_capability_when_no_tools(self):
        """When no tools found, a fallback capability is assigned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir)
            server_dir = src_dir / "empty-mcp-server"
            server_dir.mkdir()

            atoms = scan_mcp_servers(src_dir)
            assert len(atoms) == 1
            assert atoms[0]["capabilities"] == ["mcp/empty/invoke"]
