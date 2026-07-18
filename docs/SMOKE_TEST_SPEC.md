# Yuanzi 原子 Smoke Test 规范

> 版本 1.0 | M3 任务 3.5 | 适用于所有注册原子

---

## 什么是 Smoke Test

Smoke test（冒烟测试）是每个原子上线前必须通过的**最小质量门禁**。它不追求覆盖率，
而是验证原子的核心功能在基本条件下能正常工作，不会一启动就崩溃。

## 适用范围

- `atoms/` 下所有示例原子
- `yuanzi-atoms/` 下所有运行时原子
- `yuanzi-atom-templates/` 生成的新原子

---

## 测试结构

每个原子目录下必须有 `tests/` 子目录：

```
<atom-id>/
├── core.py
├── server.py
├── requirements.txt
├── Dockerfile
└── tests/
    ├── __init__.py
    ├── test_core.py          # 核心逻辑测试
    └── test_integration.py   # 服务器集成测试（可选）
```

---

## 必测场景（Tier 1 — 必须）

每个原子 smoke test 必须覆盖以下 5 类场景：

### 1. Happy path — 正常输入返回 success

```python
def test_happy_path(core):
    result = core.handler({"valid": "input"})
    assert result["status"] == "success"
    assert "data" in result
```

### 2. Missing required — 缺少必填字段返回 error

```python
def test_missing_required(core):
    result = core.handler({})
    assert result["status"] == "error"
    assert "message" in result
```

### 3. Invalid input — 非法输入不崩溃

```python
def test_invalid_input(core):
    result = core.handler({"bad": None, "worse": object()})
    assert result["status"] in ("error", "success")
    # 关键：不抛出未捕获异常
```

### 4. Edge case — 边界值正确处理

```python
def test_edge_case(core):
    result = core.handler({"count": 0, "text": ""})
    assert result["status"] == "success"  # 或明确的 error
```

### 5. Output format — 输出格式符合标准

```python
def test_output_format(core):
    result = core.handler({"input": "test"})
    assert "status" in result
    assert result["status"] in ("success", "error")
    if result["status"] == "success":
        assert "data" in result
    else:
        assert "message" in result
```

## 推荐场景（Tier 2 — 建议）

对于复杂原子，额外覆盖：

| 场景 | 说明 | 示例 |
|------|------|------|
| 大输入处理 | 输入数据接近上限 | `max_size` 边界 |
| 特殊字符 | Unicode、emoji、转义字符 | 中文、\x00、😀 |
| 并发安全 | 原子是否线程安全 | pytest-xdist 多进程 |
| 超时行为 | 长时间运行的行为 | timeout 参数 |

## 原子类型特定要求

### function 类原子（纯计算）

```python
# 额外要求：输入类型转换正确
def test_type_coercion(core):
    result = core.handler({"a": "10", "b": "20"})
    assert result["data"]["result"] == 30.0
```

### external 类原子（有网络调用）

```python
# 额外要求：无网络时不崩溃
def test_offline_graceful(core):
    result = core.handler({"url": "http://unreachable.example"})
    assert result["status"] == "error"
    assert "message" in result
```

### mcp-server 类原子（注册原子）

```python
# 额外要求：签名可计算
def test_signature_computable():
    from registry import compute_signature
    sig = compute_signature(atom_dict)
    assert len(sig) == 64  # full sha256 hex
```

### data 类原子（数据源）

```python
# 额外要求：schema 输出格式稳定
def test_schema_stable(core):
    result = core.handler({"query": "SELECT 1"})
    assert isinstance(result.get("data"), dict)
```

---

## 运行命令

```bash
# 单个原子 smoke test
python -m pytest <atom-id>/tests/test_core.py -v

# 所有示例原子（开发机）
python -m pytest atoms/tests/ -v

# 带覆盖率
python -m pytest atoms/tests/ --cov=atoms --cov-report=term-missing

# 在 CI 中（快速失败模式）
python -m pytest atoms/tests/ -v --tb=short -x
```

---

## CI 集成

CI 中 smoke test 作为独立 job 运行（见 `.github/workflows/ci.yml`）：

```yaml
- name: Example atom smoke tests
  run: |
    python -m pytest atoms/tests/ -v --tb=short
    yuanzi validate yuanzi-atom-templates/examples/com.example.sum
    yuanzi test --no-validate yuanzi-atom-templates/examples/com.example.sum
```

---

## 验收标准

原子 smoke test 全部通过才算质量门禁通过：

- [ ] 5 个 Tier 1 场景全部覆盖
- [ ] `python -m pytest <atom>/tests/` 零失败
- [ ] CI pipeline 标记为绿色
- [ ] 输出格式符合 `{"status": "success|error", "data": {...}, "message": "..."}`

---

## 与 pre-commit 的关系

Smoke test **不**在 pre-commit hook 中运行（太慢），只在 CI 和手动 `yuanzi test` 中运行。
Pre-commit hook 只跑格式化 + lint。
