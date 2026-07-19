"""结构层：表名常量、保留命名空间、异常、数据模型与迁移包装。

由 registry.py 拆分而来（ISOLATION_HARDENING_PLAN 加固1），纯结构移动，逻辑零变化。
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


REGISTRY_TABLE = "atom_registry"
AUDIT_TABLE = "atom_audit_log"
VERSIONS_TABLE = "atom_versions"

# 内置基础原子的保留命名空间，禁止注册/删除（加固4）
RESERVED_PREFIXES = ("system.", "yuanzi.")


class ConcurrentModificationError(Exception):
    """乐观锁冲突：写入时 version_counter 已被其他进程修改（加固2）。"""


@dataclass
class AtomRegistration:
    atom_id: str
    name: str
    version: str
    description: str
    purpose: Dict[str, Any]
    architecture: Dict[str, Any]
    ownership: Dict[str, Any]
    signature: Dict[str, str]
    lifecycle: Dict[str, Any] = field(default_factory=dict)
    classification: Dict[str, Any] = field(default_factory=dict)
    compliance: Dict[str, Any] = field(default_factory=dict)
    quality: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    alias: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_registry_schema(conn: sqlite3.Connection) -> None:
    """确保库结构为最新。

    DDL 的唯一权威来源是 migrations/*.sql（SCHEMA_AUTHORITY.md），
    本函数只是 migrate(conn) 的兼容包装（BUG-026）。
    """
    from migrations import migrate

    migrate(conn)
