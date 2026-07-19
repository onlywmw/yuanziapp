"""Atom Registry v2

提供原子的提交、审核、注册、去重、状态流转、审计日志等功能。
注册信息必须满足 atom-registry-schema.json 定义的完整字段。

包结构（ISOLATION_HARDENING_PLAN 加固1，原单文件 registry.py 拆分）：
- schema.py    表名常量 / 保留命名空间 / 异常 / 数据模型 / 迁移包装
- hashing.py   能力与身份指纹、完整签名
- audit.py     审计日志与 M6.4 哈希链
- core.py      提交 / 审核 / 状态流转 / 查询
- probe.py     健康探测（CIDR 白名单 + DNS 钉扎 + 乐观锁重试）
- versions.py  版本归档 / 列举 / 回滚
- deps.py      依赖图解析
- stats.py     统计 / 导出 / 审计查询 / 哈希回填

本模块全量 re-export，既有 `import registry` / `from registry import xxx`
调用方（api.py、marketplace.py、federation.py、embeddings.py、recommend.py、
probe_atoms.py、register_mcp_atoms.py、generate_registry_ledger.py、测试）零改动。
私有助手一并 re-export，保持拆分前模块属性面 100% 兼容。
"""

from __future__ import annotations

import urllib.error  # noqa: F401  保持 registry.urllib 属性链兼容（tests/test_probe.py 钉住该路径打桩）
import urllib.parse  # noqa: F401
import urllib.request  # noqa: F401

from .audit import (
    _audit,
    _compute_chain_hash,
    backfill_audit_chain,
    verify_audit_chain,
)
from .core import (
    ALLOWED_TRANSITIONS,
    _archive_version,
    _insert_or_update,
    _row_to_atom,
    _transition_allowed,
    get_atom,
    list_atoms,
    review_atom,
    set_atom_status,
    submit_atom,
)
from .deps import resolve_dependencies
from .hashing import (
    _canonical_json,
    _function_fingerprints,
    compute_content_hash,
    compute_identity_hash,
    compute_signature,
)
from .probe import (
    _ALLOWED_PROBE_SCHEMES,
    _DEFAULT_PROBE_CIDRS,
    _PROBEABLE_STATUSES,
    _PROBE_DNS_LOCK,
    _allowed_probe_networks,
    _pinned_dns,
    _probe_address_error,
    _probe_once,
    _resolve_host,
    probe_atom,
    probe_atoms,
)
from .schema import (
    AUDIT_TABLE,
    REGISTRY_TABLE,
    RESERVED_PREFIXES,
    VERSIONS_TABLE,
    AtomRegistration,
    ConcurrentModificationError,
    ensure_registry_schema,
    now_iso,
)
from .stats import (
    backfill_content_hashes,
    compute_registry_stats,
    dump_registry,
    get_audit_log,
)
from .versions import (
    _row_to_version,
    get_atom_version,
    list_atom_versions,
    rollback_atom,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "AUDIT_TABLE",
    "AtomRegistration",
    "ConcurrentModificationError",
    "REGISTRY_TABLE",
    "RESERVED_PREFIXES",
    "VERSIONS_TABLE",
    "backfill_audit_chain",
    "backfill_content_hashes",
    "compute_content_hash",
    "compute_identity_hash",
    "compute_registry_stats",
    "compute_signature",
    "dump_registry",
    "ensure_registry_schema",
    "get_atom",
    "get_atom_version",
    "get_audit_log",
    "list_atom_versions",
    "list_atoms",
    "now_iso",
    "probe_atom",
    "probe_atoms",
    "resolve_dependencies",
    "review_atom",
    "rollback_atom",
    "set_atom_status",
    "submit_atom",
    "verify_audit_chain",
]
