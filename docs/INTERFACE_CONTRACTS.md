# Yuanzi 接口契约注册表

> **性质**: 规范性文档 — 所有公开函数的唯一权威契约定义
> **规则**: 接口变更必须先更新本文档，再改代码。契约测试验证本文档。
> **版本**: 2.0 — **以代码为准重新生成于 2026-07-19**（事实来源：`mcp-yuanzi-bridge/registry.py`、`mcp-yuanzi-bridge/api.py`、`mcp-yuanzi-bridge/migrations/`）
> **变更记录**: v1.0 → v2.0：状态机 4 态→6 态（补 probing/unreachable）；probe_atom 签名与返回键按实现重写（BUG-031 闭环）；API 端点 13→39 全量清点；补 M6 认证/RBAC 条款、迁移清单 001~013；读路由认证由"可选"更正为"全员强制 Bearer"（/health 豁免，BUG-038 已立案）。

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
契约版本: v2.0

输入:
  conn: sqlite3.Connection
  atom: dict  包含 atom_id, name, version, purpose, architecture, ownership, lifecycle
  actor: str  操作者标识

输出:
  成功: {"success": true, "atom_id": str, "signature": str, "status": "submitted"}
  保留命名空间: {"success": false, "error": "reserved_namespace", "message": str}
        # atom_id 以 system. / yuanzi. 开头（RESERVED_PREFIXES，加固4）
  重复签名: {"success": false, "error": "duplicate_signature", "message": str}
        # 含两类：signature_hash 撞车；content_hash 相同但 atom_id 不同（换皮能力，BUG-006/016）
  缺少 atom_id: ValueError

副作用:
  - 写入 atom_registry（ON CONFLICT 更新，version_counter +1）
  - 内容快照归档 atom_versions（同版本重复提交则更新）
  - 记审计（action="submit"，含 chain_hash 哈希链，M6.4）
```

### 1.2 `review_atom(conn, atom_id, approved, reviewer="system", comments="", score=None) -> dict`

```
契约版本: v2.0

输出:
  成功: {"success": true, "atom_id": str, "status": "registered"|"rejected"}
  不存在: {"success": false, "error": "not_found", "message": str}
```

### 1.3 `set_atom_status(conn, atom_id, status, actor="system", detail="") -> dict`

```
契约版本: v2.0（六态状态机，ALLOWED_TRANSITIONS 是唯一事实来源，BUG-019）

合法状态: registered / probing / running / unreachable / offline / deprecated
        （submitted / rejected 为审核阶段状态，不参与本表流转）

允许的状态转换:
  registered  → probing | running | unreachable | offline | deprecated
  probing     → running | unreachable | offline | deprecated
  running     → probing | unreachable | offline | deprecated | registered
  unreachable → probing | running | offline | deprecated
  offline     → probing | running | unreachable | deprecated | registered
  deprecated  → registered

输出:
  成功: {"success": true, "atom_id": str, "old_status": str, "new_status": str}
  不存在: {"success": false, "error": "not_found", "message": str}
  非法转换: {"success": false, "error": "invalid_transition", "message": str}

副作用: version_counter +1；记审计（action="status_change"）
```

### 1.4 `get_atom(conn, atom_id) -> dict | None`

```
契约版本: v2.0

输出: 完整原子 dict 或 None
dict 键: atom_id, name, version, description, purpose, architecture,
         ownership, classification, compliance, quality, runtime,
         lifecycle, signature_hash, signature_algorithm, alias,
         created_at, submitted_at, registered_at, updated_at,
         reviewed_at, reviewed_by, review_comments, review_score,
         content_hash, identity_hash, version_counter
        # version_counter 为乐观锁字段（迁移 013，加固2）
        # *_json 列已反序列化为 dict（去掉 _json 后缀）；alias 为 list
```

### 1.5 `list_atoms(conn, status=None, category=None, search=None) -> list[dict]`

```
契约版本: v2.0

输入:
  status: str|None   按 lifecycle.status 过滤
  category: str|None 按 classification.category 过滤
  search: str|None   关键词搜索 atom_id/name/alias (LIKE %search%)

输出: 原子 dict 列表，按 atom_id 排序（无分页/排序参数——M4 契约承诺的
      page/size/sort/order 未实现，见 DESIGN_M4_REGISTRY_API 文首横幅）
```

### 1.6 `list_atom_versions(conn, atom_id) -> list[dict]`

```
契约版本: v2.0

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
按 created_at DESC, id DESC 排序
```

### 1.7 `get_atom_version(conn, atom_id, version) -> dict | None`

```
契约版本: v2.0

输出: 完整版本快照 dict 或 None（*_json 列已反序列化）
```

### 1.8 `rollback_atom(conn, atom_id, version, actor="system") -> dict`

```
契约版本: v2.0

输出:
  成功: {"success": true, "atom_id": str, "version": str}
  版本不存在: {"success": false, "error": "version_not_found", "message": str}
  原子不存在: {"success": false, "error": "not_found", "message": str}

行为: 只替换内容与 version 字段，当前 lifecycle 状态保留；
      回滚记一条审计（action="rollback"）；归档版本记录不受影响。
```

### 1.9 `probe_atom(conn, atom_id, timeout=2.0, actor="probe", max_retries=3) -> dict`

```
契约版本: v2.0（按实现重写，闭环 BUG-024/BUG-031；替代 v1.0 全部条款）

输入:
  timeout: float      单次请求超时秒（默认 2.0，与 CLI 一致，BUG-027）
  actor: str          审计 actor（默认 "probe"）
  max_retries: int    乐观锁冲突重试上限（加固2）；超限抛
                      ConcurrentModificationError

输出（成功执行探测）:
  {
    "success": true,
    "atom_id": str,
    "ok": bool,              # 仅 2xx 为 true（BUG-027 收紧，3xx 不算健康）
    "probe_status": str,     # "ok" | "http_<code>" | "connection_error"
    "latency_ms": float,
    "old_status": str,
    "new_status": str
  }

输出（未发请求或前置失败）:
  原子不存在: {"success": false, "error": "not_found", "message": str}
  无端点:     {"success": false, "atom_id": str, "error": "no_endpoint",
               "message": str, "old_status": str, "new_status": str}
  非法 URL:   {"success": false, "atom_id": str, "error": "invalid_url",
               "message": str, "old_status": str, "new_status": str}
  地址越界:   {"success": false, "atom_id": str, "error": "blocked_address",
               "message": str, "old_status": str, "new_status": str}

探测后副作用:
  - 两阶段写入（BUG-017）：可探测原子先置 probing，再按结果流转；
    结果不变时把 probing 标记还原
  - 目标状态: 2xx → running；非 2xx / 连接错误 → unreachable
    （一次失败即置 unreachable；consecutive_failures 只作记录，不作阈值）
  - 仅当 old_status ∈ {registered, probing, running, unreachable, offline}
    （_PROBEABLE_STATUSES）时才改生命周期；deprecated/rejected 只记录结果
  - runtime_json 写入 last_probe_at / last_probe_status /
    last_probe_latency_ms / consecutive_failures
  - 审计节流（BUG-022）：仅生命周期变化或探测结果类别变化时记审计；
    no_endpoint / invalid_url / blocked_address 也留痕（BUG-018）
  - 写入带 version_counter 条件（乐观锁），冲突时整体重读重试

安全约束:
  - scheme 仅允许 http/https（BUG-014/020）
  - 目标地址默认仅允许 127.0.0.0/8 + ::1/128；可用环境变量
    YUANZI_PROBE_ALLOWED_CIDR 追加网段（逗号分隔，M6.5b /
    裁决 2026-07-18-01）；env 全为畸形项时 fail-closed 全拒（BUG-033）
  - DNS 解析带超时、校验与请求落在同一临界区 + getaddrinfo 钉扎，
    防 DNS 重绑定 TOCTOU（BUG-033）
```

### 1.10 `probe_atoms(conn, atom_ids=None, timeout=2.0, actor="probe") -> list[dict]`

```
契约版本: v2.0

输入:
  atom_ids: list[str]|None  指定原子列表，None=注册表里的所有原子

输出: [probe_atom_result, ...]
     单个原子异常不中断批次，失败项为
     {"success": false, "atom_id": str, "error": "probe_exception",
      "message": str}（BUG-014）
```

### 1.11 `resolve_dependencies(conn, atom_id) -> dict`

```
契约版本: v2.0（BUG-023 已闭环，键名以此为准）

输出:
  {
    "ok": bool,              # 所有依赖可解析且无循环
    "atom_id": str,
    "order": [str],          # 拓扑排序的 atom_id (含自身排在最后)
    "missing": [str],        # 不存在的依赖 atom_id（升序）
    "cycles": [[str, ...]],  # 循环依赖路径（每条为构成环的 atom_id 序列）
    "deps": [                # 解析后的直接依赖
      {
        "atom_id": str,
        "name": str,
        "status": str        # 依赖不存在时为 "missing"
      }
    ]
  }

特殊情况:
  自身不存在: ok=false, missing=[atom_id]
  直接自循环: ok=false, cycles=[[atom_id, atom_id]]
```

### 1.12 `compute_registry_stats(conn) -> dict`

```
契约版本: v2.0

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
契约版本: v2.0

输出:
  {
    "schema_version": str,    # migrations.current_version() 的字符串形式
    "generated_at": str,
    "stats": dict,            # compute_registry_stats() 输出
    "atoms": [dict],          # list_atoms() 输出
    "audit_log": [dict]       # 仅在 include_audit=True 时非空
  }
```

### 1.14 `get_audit_log(conn, atom_id=None) -> list[dict]`

```
契约版本: v2.0

输出: [{"id": int, "atom_id": str, "action": str, "old_status": str|null,
        "new_status": str|null, "actor": str, "detail": str,
        "created_at": str, "chain_hash": str|null}]
按 created_at DESC 排序；chain_hash 为 M6.4 哈希链字段（旧行可能为空）
```

### 1.15 `verify_audit_chain(conn) -> dict`（M6.4）

```
契约版本: v2.0

行为: 重算审计哈希链，检测篡改。chain_hash 为空的迁移前旧行
     （legacy_rows）不参与校验。

输出:
  通过: {"valid": true, "total_rows": int, "legacy_rows": int,
         "broken_at_row": null, "verified_at": str}
  失败: {"valid": false, "total_rows": int, "legacy_rows": int,
         "broken_at_row": int, "expected": str, "actual": str,
         "verified_at": str}
```

### 1.16 回填与哈希工具函数

```
backfill_audit_chain(conn) -> int
  为迁移前的旧审计行补算 chain_hash（按 id 顺序重链）。返回回填行数。

backfill_content_hashes(conn) -> int
  回填历史行的 content_hash / identity_hash（迁移 005 之后执行）。
  返回回填行数。

compute_content_hash(atom) -> str
  能力指纹（功能含 input/output schema、架构、依赖、接口），
  能力完全相同的原子得到相同值。sha256 hex（64 字符）。

compute_identity_hash(atom) -> str
  身份指纹（atom_id、版本、author、license）。sha256 hex。

compute_signature(atom) -> str
  完整签名（去重主键）= content_hash + identity_hash 组合的 sha256 hex。

ensure_registry_schema(conn) -> None
  migrate(conn) 的兼容包装（BUG-026）；DDL 唯一权威源是 migrations/*.sql。
```

### 1.17 模块级常量与异常

```
RESERVED_PREFIXES = ("system.", "yuanzi.")
  内置基础原子保留命名空间：submit 拦截（reserved_namespace），
  DELETE 路由 403（加固4）。

ALLOWED_TRANSITIONS: dict[str, list[str]]
  六态流转表（见 1.3），set_atom_status 与 probe_atom 的唯一事实来源。

ConcurrentModificationError(Exception)
  乐观锁冲突：写入时 version_counter 已被其他进程修改（加固2）。
  probe_atom 内部重试 max_retries 次后向上抛出。
```

---

## 2. migrations 公开接口

### 2.1 `migrate(conn) -> list[int]`

```
契约版本: v2.0

行为: 执行所有未应用的 SQL 迁移文件 (NNN_*.sql，按编号升序)。
     旧库 baseline：atom_registry 已存在而 schema_migrations 为空时，
     001 只记录不执行。每个迁移在显式事务中执行，失败回滚。
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

### 2.6 迁移清单（001~013，2026-07-19 与 `migrations/` 目录逐一核对）

| 编号 | 文件 | 内容 |
|------|------|------|
| 001 | 001_init.sql | 注册中心 v2 基线：atom_registry + atom_audit_log |
| 002 | 002_atoms_view.sql | atoms 兼容 VIEW（APK GraphView 隐式契约） |
| 003 | 003_atom_versions.sql | atom_versions 版本归档表（M4.2） |
| 004 | 004_function_embeddings.sql | function_embeddings 函数级嵌入表（M5） |
| 005 | 005_content_hash_columns.sql | atom_registry 增 content_hash / identity_hash 列（BUG-016） |
| 006 | 006_api_tokens.sql | api_tokens 表（M6.1，取代 registry_meta 设计） |
| 007 | 007_atom_versions_changelog.sql | atom_versions 增 changelog 列 |
| 008 | 008_audit_chain.sql | atom_audit_log 增 chain_hash 哈希链（M6.4） |
| 009 | 009_workflows.sql | workflows / workflow_runs 表（M7） |
| 010 | 010_atom_reviews.sql | atom_reviews 评分评论表（M7） |
| 011 | 011_federation_peers.sql | federation_peers 表（M7 联邦） |
| 012 | 012_atoms_view_coalesce.sql | atoms VIEW COALESCE 重建（加固3） |
| 013 | 013_optimistic_lock.sql | atom_registry 增 version_counter 乐观锁（加固2） |

---

## 3. API 端点契约 (api.py, port 8081)

### 3.1 通用

```
所有响应: Content-Type: application/json
错误响应: {"detail": str}（HTTPException；422 校验错误为 FastAPI 默认结构）

认证 (M6 已实施):
  Authorization: Bearer <token>
  token 来源: env YUANZI_API_TOKEN > api_tokens 表（006 迁移）
             > 皆空则开发模式放行（默认！部署方须显式设置 token）
  角色等级: admin > registry > viewer；probe 为独立角色（仅探测路由）
  除 /health 外所有路由（含 GET）均强制 Bearer —— 读路由"可选认证"
  的 v1.0 条款作废。/health 豁免已立案 BUG-038 备档。
```

### 3.2 端点清单（39 个，逐一清点自 api.py 路由装饰器，行号为 2026-07-19 快照）

| # | 方法 | 路径 | 角色 | 说明 / 契约键 |
|---|------|------|------|----------------|
| 1 | GET | /health | 公开 | `{"status": "ok"}`（api.py:112） |
| 2 | GET | /stats | viewer | `compute_registry_stats()` 输出（:116） |
| 3 | GET | /atoms | viewer | `list_atoms()` 裸 List；query: status/category/search（:120） |
| 4 | POST | /atoms | registry | `submit_atom()` 输出；201；409 冲突（:128） |
| 5 | DELETE | /atoms/{atom_id} | admin | `{"success": true, "atom_id": str}`；system./yuanzi. → 403（:135） |
| 6 | GET | /atoms/{atom_id} | viewer | `get_atom()` 输出；404（:150） |
| 7 | POST | /atoms/{atom_id}/review | admin | `review_atom()` 输出；body: approved/reviewer/comments/score（:157） |
| 8 | POST | /atoms/{atom_id}/status | registry | `set_atom_status()` 输出；body: status/detail（:171） |
| 9 | POST | /atoms/{atom_id}/probe | probe | `probe_atom()` 输出；query: timeout=2.0（:179） |
| 10 | POST | /probe | probe | 批量探测 `{"total", "reachable", "results"}`（:187） |
| 11 | GET | /atoms/{atom_id}/versions | viewer | `list_atom_versions()` 输出（:197） |
| 12 | GET | /atoms/{atom_id}/versions/{version} | viewer | `get_atom_version()` 输出（:203） |
| 13 | POST | /atoms/{atom_id}/rollback/{version} | admin | `rollback_atom()` 输出（:213） |
| 14 | GET | /atoms/{atom_id}/dependencies | viewer | `resolve_dependencies()` 输出（:220） |
| 15 | GET | /atoms/{atom_id}/recommendations | viewer | `{"atom_id", "recommendations"}`；query: limit=5（M5，:226） |
| 16 | GET | /atoms/{atom_id}/combination | viewer | 依赖闭包拓扑序（M5，:238） |
| 17 | POST | /search | viewer | 语义搜索；q/limit=10/provider=mock/model/min_score（:247） |
| 18 | GET | /search | viewer | 同上（GET 兼容保留，BUG-028 备档）（:257） |
| 19 | POST | /tokens | admin | 创建 API token；201；body: token/role/description/expires_at（:296） |
| 20 | GET | /tokens | admin | token 列表（:309） |
| 21 | DELETE | /tokens/{token_id} | admin | 吊销；`{"success": true, "id": int}`（:313） |
| 22 | POST | /atoms/{atom_id}/reviews | registry | 添加评分评论；201；body: author/rating/text（M7，:321） |
| 23 | GET | /atoms/{atom_id}/reviews | viewer | 评论列表（M7，:331） |
| 24 | GET | /atoms/{atom_id}/rating | viewer | `composite_score()` 综合分（M7，:337） |
| 25 | GET | /marketplace | viewer | 榜单；query: tab=hot\|top\|new, limit=20（M7，:343） |
| 26 | POST | /workflows | registry | 保存工作流（5 条验证）；201；422 带 errors/warnings（M7，:349） |
| 27 | GET | /workflows | viewer | 工作流列表（M7，:359） |
| 28 | GET | /workflows/{workflow_id} | viewer | 工作流详情（M7，:363） |
| 29 | POST | /workflows/{workflow_id}/validate | viewer | 重跑验证，返回 errors/warnings（M7，:372） |
| 30 | POST | /workflows/{workflow_id}/run | registry | 拓扑分层执行，返回 run（M7，:381） |
| 31 | GET | /workflows/{workflow_id}/runs | viewer | 运行历史（M7，:390） |
| 32 | GET | /runs/{run_id} | viewer | 单次运行详情（M7，:394） |
| 33 | GET | /federation/export | viewer | 对外原子元数据（不含 runtime/endpoint）（M7，:401） |
| 34 | POST | /federation/peers | admin | 添加 peer；201；body: name/base_url/trust_level（M7，:406） |
| 35 | GET | /federation/peers | viewer | peer 列表（M7，:413） |
| 36 | DELETE | /federation/peers/{peer_id} | admin | 移除 peer（M7，:417） |
| 37 | POST | /federation/sync/{peer_id} | admin | 同步 peer 原子元数据（M7，:423） |
| 38 | GET | /audit/verify | admin | `verify_audit_chain()` 输出（M6.4，:433） |
| 39 | GET | /audit | viewer | `get_audit_log()` 输出；query: atom_id（:438） |

注：路由**无 `/api/v1` 前缀**，全部挂根路径（M4~M7 文档的前缀契约为
文档侧偏差，见各阶段文档文首横幅）。Chaquopy 入口
`start_server(files_dir, host="127.0.0.1", port=8081)`（api.py:448）。

---

## 4. 契约测试模板

`tests/test_contracts.py` 应包含以下结构的测试：

```python
def test_submit_atom_contract():
    """验证 submit_atom 返回值结构符合契约 v2.0"""
    result = submit_atom(conn, valid_atom)
    assert result["success"] is True
    assert "atom_id" in result
    assert "signature" in result
    assert result["status"] == "submitted"

def test_resolve_dependencies_contract():
    """验证 resolve_dependencies 返回值键名符合契约 v2.0"""
    result = resolve_dependencies(conn, atom_id)
    assert "ok" in result
    assert "order" in result       # ← 这个键必须有
    assert "missing" in result     # ← 这个键必须有
    assert "cycles" in result      # ← 这个键必须有
    assert "deps" in result
    assert isinstance(result["order"], list)
    assert isinstance(result["cycles"], list)

def test_probe_atom_contract():
    """验证 probe_atom 返回键符合契约 v2.0（BUG-031 闭环）"""
    result = probe_atom(conn, atom_id)
    assert "probe_status" in result
    assert "old_status" in result
    assert "new_status" in result
```

---

> **本文档是接口的"宪法"**。代码实现必须符合本文档，而非本文档符合代码。
> 接口变更流程: 更新本文档 → 更新契约测试 → 修改实现 → CI 通过。
> v2.0 为重生成基线：此前 v1.0 已系统性滞后于实现（BUG-031 等），
> 本次以代码为事实来源对齐后恢复"代码必须符合文档"的约束力。
