#!/usr/bin/env python3
"""Generate human-readable and machine-readable atom registry ledgers.

Deprecated in favor of :func:`register_mcp_atoms.write_ledger`, which
produces richer ledgers including v2 schema fields and category stats.
This script is kept for debugging and ad-hoc reporting.

Reads from the atom_registry table via :func:`registry.list_atoms` and
writes Markdown, CSV, and JSON reports to this directory.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from pathlib import Path

from registry import dump_registry, list_atoms

OUTPUT_DIR = Path(__file__).parent
DB_PATH = os.environ.get(
    "YUANZI_DB_PATH",
    "/data/data/com.termux/files/home/yuanzi-data/agent.db",
)


def generate_markdown(atoms: list) -> str:
    """Generate a Markdown ledger from a list of atom dicts."""
    lines = [
        "# 原子注册登记表",
        "",
        "> 注册标准：名称 + 作用 + 架构 + 签名去重",
        "",
        f"**登记总数**：{len(atoms)} 个原子",
        "",
        "## 登记表",
        "",
        "| 序号 | 原子 ID | 名称 | 作用摘要 | 架构类型 | 运行时 | 状态 | 签名 |",
        "|------|---------|------|---------|---------|------|------|------|",
    ]
    for idx, atom in enumerate(atoms, 1):
        purpose = atom.get("purpose", {})
        arch = atom.get("architecture", {})
        lifecycle = atom.get("lifecycle", {})
        sig = atom.get("signature_hash", "")[:12]
        lines.append(
            f"| {idx} | `{atom['atom_id']}` | {atom.get('name', '')} | "
            f"{purpose.get('summary', '')[:60]} | "
            f"{arch.get('type', '')} | {arch.get('runtime', '')} | "
            f"{lifecycle.get('status', '')} | `{sig}...` |"
        )

    lines.extend(
        [
            "",
            "## 注册字段说明",
            "",
            "- **atom_id**：全局唯一标识",
            "- **name**：人类可读名称",
            "- **purpose**：作用描述（summary + functions + input + output）",
            "- **architecture**：架构（type/runtime/interface/state/execution/dependencies/hosting）",
            "- **signature_hash**：去重指纹，同签名原子只注册一次",
            "- **status**：submitted / registered / running / offline / deprecated",
        ]
    )
    return "\n".join(lines)


def generate_csv(atoms: list) -> str:
    """Generate a CSV ledger from a list of atom dicts."""
    csv_path = OUTPUT_DIR / "ATOM_REGISTRY_LEDGER.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "序号",
                "atom_id",
                "名称",
                "类别",
                "状态",
                "版本",
                "签名",
                "功能数",
                "source_url",
            ]
        )
        for idx, atom in enumerate(atoms, 1):
            purpose = atom.get("purpose", {})
            classification = atom.get("classification", {})
            lifecycle = atom.get("lifecycle", {})
            ownership = atom.get("ownership", {})
            writer.writerow(
                [
                    idx,
                    atom["atom_id"],
                    atom.get("name", ""),
                    classification.get("category", ""),
                    lifecycle.get("status", ""),
                    atom.get("version", "1.0.0"),
                    atom.get("signature_hash", ""),
                    len(purpose.get("functions", [])),
                    ownership.get("source_url", ""),
                ]
            )
    return str(csv_path)


def generate_json(conn: sqlite3.Connection) -> str:
    """Generate a JSON ledger using the registry dump."""
    json_path = OUTPUT_DIR / "ATOM_REGISTRY_LEDGER.json"
    data = dump_registry(conn, include_audit=False)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(json_path)


def main() -> None:
    if not Path(DB_PATH).exists():
        print(f"[WARNING] Database not found: {DB_PATH}")
        print("Set YUANZI_DB_PATH to point to a valid agent.db")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        atoms = list_atoms(conn)
        print(f"从注册表读取到 {len(atoms)} 个原子")

        md = generate_markdown(atoms)
        md_path = OUTPUT_DIR / "ATOM_REGISTRY_LEDGER.md"
        md_path.write_text(md, encoding="utf-8")
        print(f"Markdown 登记表：{md_path}")

        csv_path = generate_csv(atoms)
        print(f"CSV 登记表：{csv_path}")

        json_path = generate_json(conn)
        print(f"JSON 登记表：{json_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
