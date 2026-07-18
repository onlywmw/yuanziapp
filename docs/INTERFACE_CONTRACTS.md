# Yuanzi 接口契约注册表

> **性质**: 规范性文档 — 所有公开函数的唯一权威契约定义
> **规则**: 接口变更必须先更新本文档，再改代码。契约测试验证本文档。
> **版本**: 1.0

---

## 使用说明

本文档是 `registry.py` 和 `api.py` 中所有公开函数的**接口契约**。

- **Eng**: 实现函数前先读本文档的契约定义。返回值必须完全匹配。
- **Arch**: 契约变更必须在此文档中记录，标注版本号和变更原因。
- **Audit**: 审查时对照本文档检查实际返回值结构。
- **CI**: 契约测试 (`tests/test_contracts.py`) 自动验证实现是否符合本文档。

---

## 1. registry.py 公开接口

### 1.1 `submit_atom(conn, atom, actor="system") -> dict`

```
契约版本: v1.0 (不可变)

输入:
  conn: sqlite3.Connection
  atom: dict  包含 atom_id, name, version, purpose, architecture, ownership, lifecycle
  actor: str  操作者标识

输出:
  成功: {"success": true, "atom_id": str, "signature": str, "status": "submitted"}
  重复签名: {"success": false, "error": "duplicate_signature", "message": str}
  缺少 atom_id: ValueError
```

### 1.2 `review_atom(conn, atom_id, approved, reviewer="system", comments="", score=None) -> dict`

```
契约版本: v1.0

输出:
  成功: {"success": true, "atom_id": str, "status": "registered"|"rejected"}
  不存在: {"success": false, "error": "not_found", "message": str}
```

### 1.3 `set_atom_status(conn, atom_id, status, actor="system", detail="") -> dict`

```
契约版本: v1.0

允许的状态转换:
  registered → running | offline | deprecated
  running    → offline | deprecated | registered
  offline    → running | deprecated | registered
  deprecated → registered

输出:
  成功: {"success": true, "atom_id": str, "old_status": str, "new_status": str}
  不存在: {"success": false, "error": "not_found", "message": str}
  非法转换: {"success": false, "error": "invalid_transition", "message": str}
```

### 1.4 `get_atom(conn, atom_id) -> dict | None`

```
契约版本: v1.0

输出: 完整原子 dict 或 None
dict 键: atom_id, name, version, description, purpose, architecture,
         ownership, classification, compliance, quality, runtime,
         lifecycle, signature_hash, signature_algorithm, alias,
         created_at, submitted_at, registered_at, updated_at,
         content_hash, identity_hash
```

### 1.5 `list_atoms(conn, status=None, category=None, search=None) -> list[dict]`

```
契约版本: v1.0

输入:
  status: str|None   按 lifecycle.status 过滤
  category: str|None 按 classification.category 过滤
  search: str|None   关键词搜索 atom_id/name/alias (LIKE %search%)

输出: 原子 dict 列表，按 atom_id 排序
```

### 1.6 `list_atom_versions(conn, atom_id) -> list[dict]`

```
契约版本: v1.0

输出: [
  {
    "version": str,        # semver
    "signature": str,      # signature_hash
    "content_hash": str,
    "changelog": str|null,
    "purpose": dict,       # 该版本的完整 purpose
    "created_at": str      # ISO 8601
  }
]
按 created_at DESC 排序
```

### 1.7 `get_atom_version(conn, atom_id, version) -> dict | None`

```
契约版本: v1.0

输出: 完整版本快照 dict 或 None
```

### 1.8 `rollback_atom(conn, atom_id, version, actor="system") -> dict`

```
契约版本: v1.0

输出:
  成功: {"success": true, ...}
  版本不存在: {"success": false, "error": "version_not_found", "message": str}
```

### 1.9 `probe_atom(conn, atom_id, timeout=5, actor="system") -> dict`

```
契约版本: v1.0 ⚠️ 当前实现不完整 (BUG-024)

输出:
  {
    "success": bool,         # 探测是否执行（非目标是否可达）
    "ok": bool,              # 目标返回 2xx/3xx
    "atom_id": str,
    "endpoint": str,
    "status_code": int|null,
    "latency_ms": float|null,
    "error": str|null,       # 连接失败原因
    "checked_at": str        # ISO 8601
  }

探测后副作用:
  - 成功 → set_atom_status(conn, atom_id, "running", actor, "probe_ok")
  - 失败 → 递增 runtime_json.consecutive_failures
          若 consecutive_failures >= 3 → set_atom_status(..., "unreachable", ...)
  - 始终写审计日志

安全约束:
  - scheme 仅允许 http/https
  - 目标地址仅允许 127.0.0.0/8 (可配置)
```

### 1.10 `probe_atoms(conn, atom_ids=None, timeout=5, actor="system") -> list[dict]`

```
契约版本: v1.0

输入:
  atom_ids: list[str]|None  指定原子列表，None=全部已注册原子

输出: [probe_atom_result, ...]
     单个原子失败不影响其他原子
```

### 1.11 `resolve_dependencies(conn, atom_id) -> dict`

```
契约版本: v1.0 ⚠️ 当前实现键名不一致 (BUG-023)

输出:
  {
    "ok": bool,              # 所有依赖可解析且无循环
    "atom_id": str,
    "order": [str],          # 拓扑排序的 atom_id (含自身排在最后)
    "missing": [str],        # 不存在的依赖 atom_id
    "cycles": [[str, str]],  # 循环依赖路径
    "deps": [                # 解析后的直接依赖
      {
        "atom_id": str,
        "name": str,
        "status": str
      }
    ]
  }

特殊情况:
  自身不存在: {"ok": false, "atom_id": str, "missing": [atom_id]}
  直接自循环: {"ok": false, "atom_id": str, "cycles": [[atom_id, atom_id]]}
```

### 1.12 `compute_registry_stats(conn) -> dict`

```
契约版本: v1.0

输出:
  {
    "total_atoms": int,
    "status_counts": {str: int},
    "category_counts": {str: int},
    "generated_at": str     # ISO 8601
  }
```

### 1.13 `dump_registry(conn, include_audit=False) -> dict`

```
契约版本: v1.0

输出:
  {
    "schema_version": str,    # 从 schema_migrations 读取
    "generated_at": str,
    "stats": dict,            # compute_registry_stats() 输出
    "atoms": [dict],          # list_atoms() 输出
    "audit_log": [dict]       # 仅在 include_audit=True 时
  }
```

### 1.14 `get_audit_log(conn, atom_id=None) -> list[dict]`

```
契约版本: v1.0

输出: [{"id": int, "atom_id": str, "action": str, "old_status": str|null,
        "new_status": str|null, "actor": str, "detail": str, "created_at": str}]
按 created_at DESC 排序
```

---

## 2. migrations 公开接口

### 2.1 `migrate(conn) -> list[int]`

```
契约版本: v1.0

行为: 执行所有未应用的 SQL 迁移文件 (001_*.sql, 002_*.sql, ...)
输出: 本次新应用的迁移版本号列表
```

### 2.2 `current_version(conn) -> int`

```
输出: 最新已应用的迁移版本号，0 = 无迁移
```

### 2.3 `applied_versions(conn) -> list[int]`

```
输出: 所有已应用的迁移版本号，升序
```

### 2.4 `pending_migrations(conn) -> list[int]`

```
输出: 未应用的迁移版本号，升序
```

### 2.5 `discover_migrations() -> list[tuple[int, str, Path]]`

```
输出: [(version, name, file_path), ...] 升序
```

---

## 3. API 端点契约 (api.py, port 8081)

### 3.1 通用

```
所有响应: Content-Type: application/json
错误响应: {"detail": str}

认证 (M6 实施后):
  所有写路由: Authorization: Bearer <token>
  读路由: 可选
```

### 3.2 端点列表

| 方法 | 路径 | 契约键 |
|------|------|--------|
| GET | /health | `{"status": "ok"}` |
| GET | /stats | `compute_registry_stats()` 输出 |
| GET | /atoms | 分页原子列表 |
| GET | /atoms/{id} | `get_atom()` 输出 |
| GET | /atoms/{id}/versions | `list_atom_versions()` 输出 |
| POST | /atoms | `submit_atom()` 输出 (201) |
| POST | /atoms/{id}/review | `review_atom()` 输出 |
| POST | /atoms/{id}/status | `set_atom_status()` 输出 |
| POST | /atoms/{id}/rollback/{v} | `rollback_atom()` 输出 |
| POST | /atoms/{id}/probe | `probe_atom()` 输出 |
| GET | /atoms/{id}/dependencies | `resolve_dependencies()` 输出 |
| POST | /search | 搜索请求 (M5) |
| GET | /audit | `get_audit_log()` 输出 |

---

## 4. 契约测试模板

`tests/test_contracts.py` 应包含以下结构的测试：

```python
def test_submit_atom_contract():
    """验证 submit_atom 返回值结构符合契约 v1.0"""
    result = submit_atom(conn, valid_atom)
    assert result["success"] is True
    assert "atom_id" in result
    assert "signature" in result
    assert result["status"] == "submitted"

def test_resolve_dependencies_contract():
    """验证 resolve_dependencies 返回值键名符合契约 v1.0"""
    result = resolve_dependencies(conn, atom_id)
    assert "ok" in result
    assert "order" in result       # ← 这个键必须有
    assert "missing" in result     # ← 这个键必须有
    assert "cycles" in result      # ← 这个键必须有
    assert "deps" in result
    assert isinstance(result["order"], list)
    assert isinstance(result["cycles"], list)
```

---

> **本文档是接口的"宪法"**。代码实现必须符合本文档，而非本文档符合代码。
> 接口变更流程: 更新本文档 → 更新契约测试 → 修改实现 → CI 通过。
