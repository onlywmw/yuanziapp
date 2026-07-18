# Yuanzi 原子 Smoke Test 规范

> 版本：v1.0 | 生效日期：2026-07-18 | 关联任务：PROJECT_PLAN 3.5

每个原子都必须附带一组**冒烟测试**（smoke tests）：最小、最快、能立刻判断
"这个原子是不是坏的"。冒烟测试不是完整测试套件，它的目标是 30 秒内给出
可信的 通过/不通过。

---

## 1. 适用范围

| kernel_type | 是否要求冒烟测试 |
|-------------|------------------|
| `python_script` | **必须**（kernel + health 两层） |
| `markdown_rules` | 暂不要求 |
| `prompt_txt` | 暂不要求 |

## 2. 目录约定

```
com.example.my-atom/
├── meta.yaml
├── server.py
├── atom/
│   ├── __init__.py
│   └── core.py
└── tests/
    ├── test_kernel.py    # 第 1 层：内核冒烟
    └── test_health.py    # 第 2 层：端点冒烟
```

文件名是约定，不是建议——`yuanzi validate` 会检查它们存在，
`yuanzi test --fast` 依赖 `-k kernel` 选中第 1 层。

## 3. 第 1 层：内核冒烟（test_kernel.py）

**目的**：不启动任何服务，直接调用 `atom.core.handle()`，验证核心逻辑没坏。

规则：

1. **只允许 import 内核模块**（`atom.core`）和测试工具（`pytest` 等）。
2. **禁止** import `server`、`requests`、`urllib`、`http`、`socket` ——
   内核冒烟必须离线、无进程、无端口。
3. 至少覆盖：一个正常输入用例 + 一个边界/空输入用例。
4. 性能预算：单条用例 < 100ms，整个文件 < 5s。
5. 不得依赖执行顺序、环境变量、外部文件（meta.yaml 除外）。

示例（模板内置）：

```python
from atom.core import handle

def test_sum_integers():
    assert handle({"a": 1, "b": 2}) == {"result": 3}

def test_sum_defaults_to_zero():
    assert handle({}) == {"result": 0}
```

## 4. 第 2 层：端点冒烟（test_health.py）

**目的**：真实启动 `server.py`，验证原子能作为服务活下去。

规则：

1. 使用 `running_server` fixture 模式：子进程拉起 server，轮询 `/health`
   等待就绪（超时 ~5s），测试结束后 terminate。
2. 启动失败必须 dump server 的 stdout/stderr，否则 CI 上无法排查。
3. 端口必须读自 `meta.yaml` 的 `runtime.port`（支持 `PORT` 环境变量覆盖），
   不允许硬编码。
4. 至少覆盖三个端点：
   - `GET /health` → 200 且 `status == "ok"`
   - `GET /meta` → 200 且 id/version 与 meta.yaml 一致
   - `POST /run`（或原子声明的接口）→ 200 且返回结构正确
5. 性能预算：整个文件 < 30s（含 server 起停）。

## 5. 与工具链的关系

| 命令 | 行为 |
|------|------|
| `yuanzi validate <atom>` | 检查两个测试文件存在；检查 test_kernel.py 不含禁用 import |
| `yuanzi test --fast <atom>` | 只跑第 1 层（`-k kernel`），pre-commit / CI 快速门禁用 |
| `yuanzi test <atom>` | 两层全跑 |
| pre-commit 钩子 | 对改动的原子跑 validate + `--fast` |
| GitHub Actions CI | 全量（validate + test） |

## 6. 模板与示例

- `yuanzi-atom-templates/{{cookiecutter.atom_id}}/tests/` —— 新原子由
  `yuanzi init` 生成时自动带上符合本规范的两个测试文件
- `yuanzi-atom-templates/examples/com.example.sum/` —— 参考实现，
  本规范的所有规则都能在这里找到对应例子

## 7. 违反规范的处理

- 缺 `test_kernel.py` / `test_health.py` → `yuanzi validate` 报错（已有行为）
- `test_kernel.py` 含禁用 import → `yuanzi validate` 报错
- 冒烟测试失败 → pre-commit 拒绝提交 / CI 标红
