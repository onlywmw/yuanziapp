#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 awslabs/mcp-main 仓库里的 MCP 服务器批量导入 Yuanzi 图谱。

策略：
- 每个 src/*-mcp-server/ 目录视为一个能力原子
- 从 README.md 和 pyproject.toml 提取名称、描述、工具列表
- 直接写入 Yuanzi core 的 SQLite 数据库 atoms 表
- 状态标记为 "declared"（已声明，尚未运行）
"""

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Yuanzi DB 路径（在 Termux/Debian 中）
DB_PATH = os.environ.get("YUANZI_DB_PATH", "/opt/yuanzi/data/agent.db")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_first_paragraph(readme_path: Path) -> str:
    """读取 README 第一段非空文本作为描述"""
    if not readme_path.exists():
        return ""
    try:
        text = readme_path.read_text(encoding="utf-8")
        # 跳过标题，找第一段
        lines = text.splitlines()
        desc_lines = []
        started = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if started:
                    break
                continue
            if stripped.startswith("#"):
                continue
            started = True
            desc_lines.append(stripped)
            if len(" ".join(desc_lines)) > 200:
                break
        return " ".join(desc_lines)[:300]
    except Exception:
        return ""


def read_pyproject_name(pyproject_path: Path) -> str:
    """从 pyproject.toml 读取项目名"""
    if not pyproject_path.exists():
        return ""
    try:
        text = pyproject_path.read_text(encoding="utf-8")
        m = re.search(r'^\s*name\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def extract_tools(server_py_path: Path) -> List[str]:
    """简单正则提取 @mcp.tool() 装饰的函数名，支持多行装饰器参数"""
    if not server_py_path.exists():
        return []
    try:
        text = server_py_path.read_text(encoding="utf-8")
        # 支持多行 @mcp.tool(\n    name='...'\n)\nasync def xxx(
        pattern = r"@mcp\.tool(?:\([\s\S]*?\))?\s*\n(?:\s*@[^\n]+\n)*\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        return re.findall(pattern, text)
    except Exception:
        return []


def scan_mcp_servers(src_dir: Path) -> List[Dict[str, Any]]:
    """扫描所有 MCP 服务器目录"""
    atoms = []
    for server_dir in sorted(src_dir.iterdir()):
        if not server_dir.is_dir():
            continue
        name = server_dir.name
        if "-mcp-server" not in name:
            continue

        # atom id: mcp.document-loader
        short_name = name.replace("-mcp-server", "")
        atom_id = f"mcp.{short_name}"

        readme = server_dir / "README.md"

        # 找 server.py（可能在不同层级）
        server_py = None
        for py in server_dir.rglob("server.py"):
            if py.name == "server.py":
                server_py = py
                break

        # 用短目录名作为显示名，避免完整包名太长
        display_name = short_name.replace("-mcp-server", "").replace("-", " ").title()
        description = read_first_paragraph(readme) or f"AWS MCP server: {display_name}"
        tools = extract_tools(server_py) if server_py else []

        capabilities = [f"mcp/{short_name}/{tool}" for tool in tools]
        if not capabilities:
            capabilities = [f"mcp/{short_name}/invoke"]

        atoms.append(
            {
                "atom_id": atom_id,
                "label": display_name,
                "atom_type": "mcp-server",
                "endpoint": f"http://127.0.0.1:0/{short_name}",  # 占位，未运行
                "status": "declared",
                "capabilities": capabilities,
                "description": description,
                "source_dir": str(server_dir),
            }
        )

    return atoms


def import_to_yuanzi(atoms: List[Dict[str, Any]]):
    """写入 Yuanzi SQLite 数据库"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 确保表存在
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atom_id TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            atom_type TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unknown',
            capabilities TEXT DEFAULT '[]',
            updated_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """
    )

    t = now_utc()
    for atom in atoms:
        cursor.execute(
            """
            INSERT INTO atoms (atom_id, label, atom_type, endpoint, status, capabilities, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(atom_id) DO UPDATE SET
                label = excluded.label,
                atom_type = excluded.atom_type,
                endpoint = excluded.endpoint,
                status = excluded.status,
                capabilities = excluded.capabilities,
                updated_at = excluded.updated_at
        """,
            (
                atom["atom_id"],
                atom["label"],
                atom["atom_type"],
                atom["endpoint"],
                atom["status"],
                json.dumps(atom["capabilities"], ensure_ascii=False),
                t,
                t,
            ),
        )

    conn.commit()
    conn.close()


def main():
    src_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("mcp-main/src")
    if not src_dir.exists():
        print(f"[错误] 目录不存在: {src_dir}")
        sys.exit(1)

    print(f"=== 扫描 MCP 服务器: {src_dir} ===")
    atoms = scan_mcp_servers(src_dir)
    print(f"发现 {len(atoms)} 个 MCP 服务器")

    for atom in atoms[:5]:
        print(
            f"  - {atom['atom_id']}: {atom['label']} ({len(atom['capabilities'])} tools)"
        )
    if len(atoms) > 5:
        print(f"  ... 还有 {len(atoms) - 5} 个")

    print(f"\n=== 导入 Yuanzi DB: {DB_PATH} ===")
    import_to_yuanzi(atoms)
    print("导入完成")

    print("\n=== 示例原子 ===")
    print(json.dumps(atoms[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
