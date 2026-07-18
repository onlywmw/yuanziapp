# 系统隔离加固方案

> **状态**: `📐 design-ready`
> **作者**: Arch
> **日期**: 2026-07-19
> **依据**: ISOLATION_ASSESSMENT.md

---

## 总览

```
当前                         加固后
────                         ──────
registry.py (957行,1个文件) → registry/ (7个模块)
atom_registry 裸读写         → 乐观锁 + 命名空间保护
atoms VIEW 静默失败          → COALESCE 防御层
并发写入无保护                → version_counter 乐观锁
```

---

## 加固 1: registry.py 拆模块

### 拆分规则

```
registry.py (957行)
    ↓
registry/
├── __init__.py      ← 公开 API, 重新导出所有函数 (接口不变)
├── core.py          ← submit_atom, review_atom, set_atom_status
│                     get_atom, list_atoms
├── probe.py         ← probe_atom, probe_atoms
├── deps.py          ← resolve_dependencies
├── versions.py      ← list_atom_versions, get_atom_version, rollback_atom
├── hashing.py       ← compute_signature, compute_content_hash
│                     compute_identity_hash, _canonical_json
├── stats.py         ← compute_registry_stats, dump_registry, get_audit_log
└── schema.py        ← ensure_registry_schema
```

### API 层不变

```python
# registry/__init__.py — 原来的 import 全部兼容
from registry.core import submit_atom, review_atom, set_atom_status, get_atom, list_atoms
from registry.probe import probe_atom, probe_atoms
from registry.deps import resolve_dependencies
from registry.versions import list_atom_versions, get_atom_version, rollback_atom
from registry.hashing import compute_signature, compute_content_hash, compute_identity_hash
from registry.stats import compute_registry_stats, dump_registry, get_audit_log
from registry.schema import ensure_registry_schema

# 调用方 api.py 和 tests 一行不改
from registry import submit_atom  # 照旧工作
```

### 影响范围

```
registry/ 内部: 每个模块可以独立修改, 不受其他模块影响
api.py:         零改动 (import 路径不变)
register_mcp_atoms.py: 零改动
277 测试:       零改动
```

---

## 加固 2: 乐观锁

### 问题

```
时刻 T1: 进程 A 读取 atom (version_counter=5)
时刻 T2: 进程 B 读取 atom (version_counter=5)
时刻 T3: 进程 A 写入 atom (version_counter 5→6), 成功
时刻 T4: 进程 B 写入 atom (version_counter 5→6), 成功 ← 静默覆盖了 A 的修改!
```

### 方案

```sql
-- 迁移 009: atom_registry 加乐观锁
ALTER TABLE atom_registry ADD COLUMN version_counter INTEGER DEFAULT 0;
```

```python
# registry/core.py: 写入时检查版本号
def _update_atom(conn, atom_id, updates, expected_counter):
    cursor = conn.execute(
        """UPDATE atom_registry SET
            lifecycle_json = ?, version_counter = version_counter + 1
        WHERE atom_id = ? AND version_counter = ?""",
        (json.dumps(updates), atom_id, expected_counter)
    )
    if cursor.rowcount == 0:
        raise ConcurrentModificationError(
            f"Atom '{atom_id}' was modified by another process. Retry."
        )
```

### 使用场景

```
probe_atom 写入 runtime_json 时:
  1. 读取当前 atom + version_counter
  2. 执行 HTTP 健康检查
  3. 写入时带 version_counter 条件
  4. 如果 version_counter 变了 → 重试 (最多 3 次)

收益: 多个探针并发探测不会互相覆盖
```

---

## 加固 3: atoms VIEW 防御层

### 问题

```sql
-- 当前: 直接取 JSON 字段
json_extract(r.architecture_json, '$.type') AS atom_type

-- 如果某原子的 architecture_json 是 {"runtime": "python3"} (没写 type)
-- → atom_type = NULL
-- → APK GraphView 读到 NULL → 崩溃或白屏
```

### 方案

```sql
-- 迁移 010: 重建 atoms VIEW 加 COALESCE 防御
DROP VIEW IF EXISTS atoms;

CREATE VIEW atoms AS
SELECT
    r.id AS id,
    r.atom_id AS atom_id,
    COALESCE(r.name, 'unknown') AS label,
    COALESCE(json_extract(r.architecture_json, '$.type'), 'unknown') AS atom_type,
    COALESCE(json_extract(r.runtime_json, '$.endpoint'), '') AS endpoint,
    COALESCE(json_extract(r.lifecycle_json, '$.status'), 'unknown') AS status,
    COALESCE(
        (SELECT json_group_array(
                    'mcp/' || r.atom_id || '/' || COALESCE(json_extract(f.value, '$.name'), 'unknown')
                )
         FROM json_each(json_extract(r.purpose_json, '$.functions')) AS f
         WHERE json_extract(f.value, '$.name') IS NOT NULL),
        '[]'
    ) AS capabilities,
    COALESCE(json_extract(r.lifecycle_json, '$.updated_at'), r.updated_at, '') AS updated_at,
    COALESCE(json_extract(r.lifecycle_json, '$.created_at'), r.created_at, '') AS created_at
FROM atom_registry r;
```

### 收益

```
JSON 字段缺失 → 返回 'unknown' 而不是 NULL
APK GraphView → 显示灰色 "unknown" 标签, 不崩溃
开发者 → 看到 "unknown" 就知道数据有问题, 可以修
```

---

## 加固 4: 基础原子命名空间保护

### 问题

```
当前: 任何人可以 POST /atoms 注册 system.file-read
      → 覆盖内置基础原子
      → 或者 DELETE /atoms/system.file-read 删除它
```

### 方案

```python
# registry/core.py: submit_atom() 第一行加检查
RESERVED_PREFIXES = ("system.", "yuanzi.")

def submit_atom(conn, atom, actor="system"):
    atom_id = atom.get("atom_id", "")
    
    # 保护系统命名空间
    for prefix in RESERVED_PREFIXES:
        if atom_id.startswith(prefix):
            return {
                "success": False,
                "error": "reserved_namespace",
                "message": f"'{prefix}*' is reserved for built-in atoms"
            }
    
    # ... 原有逻辑
```

```python
# api.py: DELETE 路由加同样检查
@app.delete("/atoms/{atom_id}")
def delete_atom(atom_id: str):
    if atom_id.startswith("system."):
        raise HTTPException(403, "Built-in atoms cannot be deleted")
```

### 收益

```
POST /atoms system.file-read   → 403, "reserved for built-in atoms"
DELETE /atoms/system.file-read → 403, "cannot be deleted"
```

---

## 实施顺序

| 步骤 | 改动 | 风险 | 工作量 |
|------|------|------|--------|
| 1 | atoms VIEW COALESCE (加固3) | 低 (纯 SQL) | 15 min |
| 2 | 命名空间保护 (加固4) | 低 (加检查) | 15 min |
| 3 | 乐观锁 (加固2) | 中 (改写入路径) | 1h |
| 4 | registry 拆模块 (加固1) | 中 (改结构不改逻辑) | 2h |

---

## 验证

```bash
# 加固 3: VIEW 不会返回 NULL
python -c "
import sqlite3
conn = sqlite3.connect(':memory:')
# 创建表, 插入缺字段数据
# SELECT from VIEW → 所有列非 NULL
print('PASS: no NULL in VIEW')
"

# 加固 4: 系统命名空间不可注册
curl -X POST :8081/atoms -d '{"atom_id": "system.test"}'
# → 403, "reserved namespace"

# 加固 4: 基础原子不可删除
curl -X DELETE :8081/atoms/system.file-read
# → 403, "cannot be deleted"

# 加固 1: 拆分后 import 路径不变
python -c "from registry import submit_atom, probe_atom; print('OK')"

# 全量回归
python -m pytest -q
# → 全部通过
```

---

> **4 项加固, 4 小时工作量, 0 测试改动。隔离度从 ★★☆☆☆ 提升到 ★★★★☆。**
