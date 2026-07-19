"""能力/身份指纹与完整签名（纯函数，无 DB 依赖）。

由 registry.py 拆分而来（ISOLATION_HARDENING_PLAN 加固1），纯结构移动，逻辑零变化。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _function_fingerprints(purpose: Dict[str, Any]) -> List[Dict[str, Any]]:
    """功能的稳定指纹：名称 + 输入/输出 schema（如有）。"""
    fingerprints = []
    for f in purpose.get("functions", []):
        name = f.get("name")
        if not name:
            continue
        fingerprints.append(
            {
                "name": name,
                "input": f.get("input") or f.get("input_schema") or {},
                "output": f.get("output") or f.get("output_schema") or {},
            }
        )
    return sorted(fingerprints, key=lambda x: x["name"])


def compute_content_hash(atom: Dict[str, Any]) -> str:
    """能力指纹：功能（含 input/output schema）、架构、依赖、接口。

    不含任何身份字段，能力完全相同的原子会得到相同的 content_hash，
    可用于跨 atom_id 的重复能力检测。
    """
    arch = atom.get("architecture", {})
    payload = {
        "functions": _function_fingerprints(atom.get("purpose", {})),
        "type": arch.get("type", ""),
        "runtime": arch.get("runtime", ""),
        "interface": arch.get("interface", ""),
        "dependencies": sorted(set(arch.get("dependencies", []))),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def compute_identity_hash(atom: Dict[str, Any]) -> str:
    """身份指纹：atom_id、版本、归属。"""
    ownership = atom.get("ownership", {})
    payload = {
        "atom_id": atom.get("atom_id", ""),
        "version": atom.get("version", ""),
        "author": ownership.get("author", ""),
        "license": ownership.get("license", ""),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def compute_signature(atom: Dict[str, Any]) -> str:
    """完整签名（去重主键）：content_hash + identity_hash 的组合。

    返回完整的 sha256 hex（64 字符）；展示时截取前 16 位即可。
    能力指纹和身份指纹可分别通过 compute_content_hash /
    compute_identity_hash 获取。
    """
    content = compute_content_hash(atom)
    identity = compute_identity_hash(atom)
    raw = _canonical_json({"content": content, "identity": identity})
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
