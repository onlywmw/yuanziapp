#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 atom_registry 表生成人可读和机器可读的注册登记表
"""

import csv
import json
from pathlib import Path

from registry import list_registered_atoms

OUTPUT_DIR = Path(__file__).parent


def generate_markdown(atoms: list) -> str:
    lines = []
    lines.append("# 原子注册登记表\n")
    lines.append("> 注册标准：名称 + 作用 + 架构 + 签名去重\n\n")
    lines.append(f"**登记总数**：{len(atoms)} 个原子\n\n")
    lines.append("## 登记表\n")
    lines.append(
        "| 序号 | 原子 ID | 名称 | 作用摘要 | 架构类型 | 运行时 | 状态 | 签名 |"
    )
    lines.append("|------|---------|------|---------|---------|------|------|------|")

    for idx, atom in enumerate(atoms, 1):
        purpose_summary = atom["purpose"].get("summary", "")[:60]
        arch = atom["architecture"]
        lines.append(
            f"| {idx} | `{atom['atom_id']}` | {atom['name']} | {purpose_summary} | "
            f"{arch.get('type', '')} | {arch.get('runtime', '')} | {atom.get('status', '')} | "
            f"`{atom['signature']}` |"
        )

    lines.append("\n## 注册字段说明\n")
    lines.append("- **atom_id**：全局唯一标识\n")
    lines.append("- **name**：人类可读名称\n")
    lines.append("- **purpose**：作用描述（summary + functions + input + output）\n")
    lines.append(
        "- **architecture**：架构信息（type/runtime/interface/state/execution/dependencies/hosting）\n"
    )
    lines.append("- **signature**：去重指纹，同签名原子只注册一次\n")
    lines.append("- **status**：registered / running / offline / deprecated\n")

    return "\n".join(lines)


def generate_csv(atoms: list) -> str:
    output = []
    output.append(
        [
            "序号",
            "atom_id",
            "名称",
            "作用摘要",
            "功能列表",
            "架构类型",
            "运行时",
            "接口",
            "状态",
            "依赖",
            "签名",
            "版本",
            "注册时间",
        ]
    )
    for idx, atom in enumerate(atoms, 1):
        purpose = atom["purpose"]
        arch = atom["architecture"]
        output.append(
            [
                idx,
                atom["atom_id"],
                atom["name"],
                purpose.get("summary", ""),
                ", ".join(purpose.get("functions", [])),
                arch.get("type", ""),
                arch.get("runtime", ""),
                arch.get("interface", ""),
                atom.get("status", ""),
                ", ".join(arch.get("dependencies", [])),
                atom["signature"],
                atom.get("version", "1.0.0"),
                atom.get("registered_at", ""),
            ]
        )

    csv_path = OUTPUT_DIR / "ATOM_REGISTRY_LEDGER.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(output)
    return str(csv_path)


def generate_json(atoms: list) -> str:
    json_path = OUTPUT_DIR / "ATOM_REGISTRY_LEDGER.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(atoms, f, ensure_ascii=False, indent=2)
    return str(json_path)


def main():
    atoms = list_registered_atoms()
    print(f"从注册表读取到 {len(atoms)} 个原子")

    md = generate_markdown(atoms)
    md_path = OUTPUT_DIR / "ATOM_REGISTRY_LEDGER.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    csv_path = generate_csv(atoms)
    json_path = generate_json(atoms)

    print(f"Markdown 登记表：{md_path}")
    print(f"CSV 登记表：{csv_path}")
    print(f"JSON 登记表：{json_path}")


if __name__ == "__main__":
    main()
