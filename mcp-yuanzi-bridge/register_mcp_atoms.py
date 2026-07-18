#!/usr/bin/env python3
"""把 mcp-main 分解出的原子注册到 Yuanzi 注册中心 v2。

输入：workspace/mcp_atoms.json（由 mcp_decomposer.py 生成）
输出：在设备 SQLite 的 atom_registry 表中写入 61 条完整注册记录
同时生成 ATOM_REGISTRY_LEDGER.md / .csv / .json
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

from registry import (
    compute_signature,
    dump_registry,
    ensure_registry_schema,
    list_atoms,
    now_iso,
    review_atom,
    submit_atom,
)

WORKSPACE = Path(__file__).resolve().parent.parent
MCP_ATOMS_PATH = Path(__file__).resolve().parent / "mcp_atoms.json"
SCHEMA_PATH = WORKSPACE / "atom-registry-schema.json"
LEDGER_DIR = Path(__file__).resolve().parent
DB_PATH = Path("/data/data/com.termux/files/home/yuanzi-data/agent.db")


def guess_category(atom_id: str, functions: List[Dict[str, Any]]) -> str:
    name_lower = atom_id.lower()
    func_names = " ".join(f.get("name", "").lower() for f in functions)
    text = f"{name_lower} {func_names}"
    if any(k in text for k in ["document", "pdf", "doc", "file", "text", "markdown", "csv", "json"]):
        return "Document & Data"
    if any(k in text for k in ["browser", "web", "http", "url", "search", "fetch", "api"]):
        return "Web & Browser"
    if any(k in text for k in ["ai", "llm", "openai", "claude", "deepseek", "embedding", "image"]):
        return "AI & Model"
    if any(k in text for k in ["database", "db", "sql", "sqlite", "postgres", "redis"]):
        return "Database"
    if any(k in text for k in ["git", "github", "gitlab", "version", "repo"]):
        return "Version Control"
    if any(k in text for k in ["slack", "telegram", "email", "discord", "message", "notify"]):
        return "Communication"
    if any(k in text for k in ["cloud", "aws", "azure", "gcp", "s3", "storage"]):
        return "Cloud & Storage"
    if any(k in text for k in ["monitor", "log", "metric", "observability"]):
        return "Observability"
    return "Integration"


def guess_maturity(name: str) -> str:
    if any(k in name.lower() for k in ["alpha", "experimental", "preview"]):
        return "experimental"
    if any(k in name.lower() for k in ["beta"]):
        return "beta"
    return "stable"


def infer_interface(functions: List[Dict[str, Any]]) -> str:
    if any("sse" in f.get("name", "").lower() or "stream" in f.get("name", "").lower() for f in functions):
        return "std-atom-http-v1 / sse"
    return "std-atom-http-v1"


def build_registry_atom(raw: Dict[str, Any]) -> Dict[str, Any]:
    """把 mcp_atoms.json 里的原始条目转成完整的注册格式 v2。"""
    atom_id = raw.get("atom_id", "")
    label = raw.get("label", "")
    description = raw.get("description", "")
    # 原始分解文件使用 capabilities 字段保存工具名
    functions = raw.get("functions", []) or [
        {"name": cap.split("/")[-1], "description": cap}
        for cap in raw.get("capabilities", [])
    ]
    source_path = raw.get("source_path", "") or raw.get("source_dir", "")

    category = guess_category(atom_id, functions)
    maturity = guess_maturity(label)
    interface = infer_interface(functions)

    # 尽量给每个功能构造简单输入/输出说明
    enriched_functions: List[Dict[str, Any]] = []
    for f in functions:
        fname = f.get("name", "")
        enriched_functions.append({
            "name": fname,
            "description": f.get("description", ""),
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        })

    atom: Dict[str, Any] = {
        "atom_id": atom_id,
        "name": label,
        "version": "1.0.0",
        "description": description,
        "alias": [label.lower().replace(" ", "-"), atom_id.split(".")[-1]],
        "purpose": {
            "summary": description,
            "detail": f"MCP server '{label}' extracted from {source_path}. Provides {len(functions)} tool(s).",
            "functions": enriched_functions,
            "input": "Depends on the specific tool being called.",
            "output": "Depends on the specific tool being called.",
            "examples": [],
        },
        "architecture": {
            "type": "mcp-server",
            "runtime": "python3.10+",
            "interface": interface,
            "state": "stateless",
            "execution": "async",
            "dependencies": [],
            "hosting": "docker",
            "resource_requirements": {
                "cpu": "0.1-0.5 cores",
                "memory": "64-256 MB",
                "disk": "10-100 MB",
                "network": "depends on tool",
            },
            "ports": [],
        },
        "ownership": {
            "author": "mcp-main",
            "maintainer": "Yuanzi Registry",
            "team": "Yuanzi",
            "organization": "Yuanzi Atom Ecosystem",
            "license": "MIT / project license",
            "source_url": source_path,
            "documentation_url": "",
            "issue_tracker": "",
        },
        "classification": {
            "category": category,
            "domain": "mcp",
            "tags": ["mcp", category.lower().replace(" & ", "-").replace(" ", "-"), "auto-registered"],
            "maturity": maturity,
        },
        "compliance": {
            "security_level": "internal",
            "data_sensitivity": "low",
            "permissions_required": ["network"],
            "network_access": "internal",
            "audit_required": True,
        },
        "quality": {
            "test_status": "untested",
            "test_coverage": 0.0,
            "documentation_level": "basic",
        },
        "runtime": {
            "endpoint": f"http://127.0.0.1:8080/mcp/{atom_id}",
            "health_url": f"http://127.0.0.1:8080/mcp/{atom_id}/health",
            "metrics_url": "",
            "logs_url": "",
        },
        "lifecycle": {
            "status": "submitted",
        },
    }
    sig = compute_signature(atom)
    atom["signature"] = {
        "hash": sig,
        "algorithm": "sha256",
        "source": "auto-computed",
    }
    return atom


def validate_atom(atom: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    """简单字段级校验（不完全实现 JSON Schema）。"""
    errors: List[str] = []
    required = schema.get("required", [])
    for k in required:
        if k not in atom or atom[k] in (None, "", {}):
            errors.append(f"Missing required field: {k}")
    for k in ["purpose", "architecture", "ownership", "lifecycle", "signature"]:
        if k in atom and not isinstance(atom[k], dict):
            errors.append(f"Field {k} must be an object")
    if "atom_id" in atom:
        aid = atom["atom_id"]
        if not aid or "." not in aid:
            errors.append("atom_id must be a reverse-domain style string")
    return errors


def sync_atoms_table(conn: sqlite3.Connection) -> int:
    """把 atom_registry 中的原子同步到旧的 atoms 表，供 Widget MCP /graph 渲染。"""
    conn.execute("""
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
    """)
    rows = conn.execute(
        "SELECT atom_id, name, purpose_json, architecture_json, lifecycle_json, runtime_json FROM atom_registry"
    ).fetchall()
    now = now_iso()
    synced = 0
    for row in rows:
        atom_id, name, purpose_json, arch_json, lifecycle_json, runtime_json = row
        purpose = json.loads(purpose_json)
        arch = json.loads(arch_json)
        lifecycle = json.loads(lifecycle_json)
        runtime = json.loads(runtime_json)
        functions = purpose.get("functions", [])
        capabilities = [f"mcp/{atom_id}/{f.get('name', '')}" for f in functions if f.get('name')]
        atom_type = arch.get("type", "atom")
        endpoint = runtime.get("endpoint", f"http://127.0.0.1:8080/mcp/{atom_id}")
        status = lifecycle.get("status", "registered")
        conn.execute("""
            INSERT INTO atoms (atom_id, label, atom_type, endpoint, status, capabilities, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(atom_id) DO UPDATE SET
                label = excluded.label,
                atom_type = excluded.atom_type,
                endpoint = excluded.endpoint,
                status = excluded.status,
                capabilities = excluded.capabilities,
                updated_at = excluded.updated_at
        """, (atom_id, name, atom_type, endpoint, status, json.dumps(capabilities, ensure_ascii=False), now, now))
        synced += 1
    conn.commit()
    print(f"Synced {synced} atoms to legacy atoms table")
    return synced


def write_ledger(conn: sqlite3.Connection, ledger_dir: Path) -> None:
    atoms = list_atoms(conn)
    stats = {
        "total": len(atoms),
        "registered": len([a for a in atoms if a.get("lifecycle", {}).get("status") == "registered"]),
        "submitted": len([a for a in atoms if a.get("lifecycle", {}).get("status") == "submitted"]),
        "rejected": len([a for a in atoms if a.get("lifecycle", {}).get("status") == "rejected"]),
        "categories": {},
    }
    for a in atoms:
        cat = a.get("classification", {}).get("category", "Uncategorized")
        stats["categories"][cat] = stats["categories"].get(cat, 0) + 1

    # Markdown ledger
    md_path = ledger_dir / "ATOM_REGISTRY_LEDGER.md"
    generated_at = conn.execute("SELECT datetime('now')").fetchone()[0]
    lines: List[str] = [
        "# Yuanzi 原子注册登记表 v2",
        "",
        f"- 生成时间：{generated_at} UTC",
        f"- 总原子数：**{stats['total']}**",
        f"- 已注册（registered）：{stats['registered']}",
        f"- 审核中（submitted）：{stats['submitted']}",
        f"- 已拒绝（rejected）：{stats['rejected']}",
        "",
        "## 按类别统计",
        "",
        "| 类别 | 数量 |",
        "|------|------|",
    ]
    for cat, cnt in sorted(stats["categories"].items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {cnt} |")
    lines.extend([
        "",
        "## 注册原子清单",
        "",
        "| 序号 | atom_id | 名称 | 类别 | 状态 | 版本 | 签名 | 功能数 |",
        "|------|---------|------|------|------|------|------|--------|",
    ])
    for idx, a in enumerate(atoms, 1):
        cat = a.get("classification", {}).get("category", "Uncategorized")
        status = a.get("lifecycle", {}).get("status", "unknown")
        func_count = len(a.get("purpose", {}).get("functions", []))
        lines.append(
            f"| {idx} | `{a['atom_id']}` | {a['name']} | {cat} | `{status}` | {a.get('version', '')} | `{a.get('signature_hash', '')[:12]}...` | {func_count} |"
        )

    lines.extend([
        "",
        "## 字段说明",
        "",
        "| 字段 | 说明 |",
        "|------|------|",
        "| `atom_id` | 全局唯一标识 |",
        "| `name` | 人类可读名称 |",
        "| `version` | 语义化版本 |",
        "| `description` | 一句话简介 |",
        "| `purpose` | 作用与能力描述（含 functions / input / output / examples） |",
        "| `architecture` | 技术架构（类型、运行时、接口、状态、依赖、资源） |",
        "| `ownership` | 归属与产权（作者、维护者、许可证、源码地址） |",
        "| `classification` | 分类（category / domain / tags / maturity） |",
        "| `compliance` | 合规与安全（安全等级、数据敏感度、权限、审计） |",
        "| `quality` | 质量（测试状态、覆盖率、文档级别） |",
        "| `runtime` | 运行时信息（endpoint / health_url） |",
        "| `lifecycle` | 生命周期状态与审核记录 |",
        "| `signature` | 去重指纹（sha256） |",
        "",
        "## 注册流程",
        "",
        "```",
        "提交(submit) → 校验(validate) → 去重(dedup) → 审核(review) → 注册(registered) → 运行(running)",
        "              ↘ 拒绝(rejected) ↗",
        "```",
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")

    # CSV ledger
    csv_path = ledger_dir / "ATOM_REGISTRY_LEDGER.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "atom_id", "name", "version", "description", "category",
            "status", "maturity", "runtime", "interface", "hosting",
            "signature_hash", "function_count", "source_url",
        ])
        for a in atoms:
            writer.writerow([
                a["atom_id"],
                a["name"],
                a.get("version", ""),
                a.get("description", ""),
                a.get("classification", {}).get("category", ""),
                a.get("lifecycle", {}).get("status", ""),
                a.get("classification", {}).get("maturity", ""),
                a.get("architecture", {}).get("runtime", ""),
                a.get("architecture", {}).get("interface", ""),
                a.get("architecture", {}).get("hosting", ""),
                a.get("signature_hash", ""),
                len(a.get("purpose", {}).get("functions", [])),
                a.get("ownership", {}).get("source_url", ""),
            ])

    # JSON ledger
    json_path = ledger_dir / "ATOM_REGISTRY_LEDGER.json"
    json_path.write_text(
        json.dumps(dump_registry(conn, include_audit=False), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Ledger written to {ledger_dir}")


def main() -> int:
    if not MCP_ATOMS_PATH.exists():
        print(f"Missing {MCP_ATOMS_PATH}", file=sys.stderr)
        return 1

    raw_atoms: List[Dict[str, Any]] = json.loads(MCP_ATOMS_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    ensure_registry_schema(conn)

    success_count = 0
    failed: List[Dict[str, Any]] = []
    for raw in raw_atoms:
        atom = build_registry_atom(raw)
        errors = validate_atom(atom, schema)
        if errors:
            failed.append({"atom_id": atom["atom_id"], "errors": errors})
            continue
        result = submit_atom(conn, atom, actor="register_mcp_atoms")
        if result.get("success"):
            review_atom(conn, atom["atom_id"], approved=True,
                        reviewer="auto-reviewer", comments="Bulk imported from mcp-main decomposition", score=0.7)
            success_count += 1
        else:
            failed.append({"atom_id": atom["atom_id"], "errors": [result.get("message", "")]})

    sync_atoms_table(conn)
    write_ledger(conn, LEDGER_DIR)
    conn.close()

    print(f"Registered {success_count}/{len(raw_atoms)} atoms; failed: {len(failed)}")
    if failed:
        print("Failures:")
        for item in failed:
            print(f"  - {item['atom_id']}: {item['errors']}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
