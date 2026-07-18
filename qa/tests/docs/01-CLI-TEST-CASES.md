# 01 - yuanzi-cli 测试用例（权威来源）

**组件**：yuanzi-cli（init / validate / test 三个命令 + meta.yaml 校验模型）
**执行环境**：Windows 11, Python 3.12.13, venv `.venv`
**说明**：本文档是测试步骤的唯一权威来源；CSV 只记录执行状态。

---

## TC-CLI-001 `--version` 显示版本号 [P2]

- **准备**：venv 中已 `pip install -e yuanzi-cli[dev]`
- **执行**：运行 `yuanzi --version`
- **断言**：退出码 0；输出包含 `yuanzi-cli 0.1.0`

## TC-CLI-002 init 使用默认模板生成原子 [P0]

- **准备**：临时空目录 `{TMP}`；不设 `YUANZI_TEMPLATES_DIR`
- **执行**：`yuanzi init com.qa.demo --output-dir {TMP}`
- **断言**：退出码 0；生成 `{TMP}/com.qa.demo/`，含 `meta.yaml`、`server.py`、`atom/core.py`、`atom/__init__.py`、`tests/test_kernel.py`、`tests/test_health.py`；meta.yaml 中 `id: com.qa.demo`

## TC-CLI-003 init 生成的原子可通过 validate [P0]

- **准备**：TC-CLI-002 生成的原子
- **执行**：`yuanzi validate {TMP}/com.qa.demo`
- **断言**：退出码 0；输出 `OK: com.qa.demo@0.1.0 is a valid Yuanzi atom`

## TC-CLI-004 init 拒绝非法 atom_id [P1]

- **准备**：临时目录
- **执行**：`yuanzi init "BAD ID!!" --output-dir {TMP}`
- **断言**（期望行为）：退出码非 0，提示 atom_id 非法，不生成目录
- **备注**：meta.py 已有 `validate_atom_id`，init 应复用

## TC-CLI-005 init 目标目录已存在时的行为 [P2]

- **准备**：先执行一次 `yuanzi init com.qa.dup -o {TMP}`
- **执行**：再次执行相同命令
- **断言**：不应静默覆盖；若报错应给出清晰人类可读提示（非 Python traceback）

## TC-CLI-006 validate 合法示例原子 [P0]

- **准备**：仓库内 `yuanzi-atom-templates/examples/com.example.sum`
- **执行**：`yuanzi validate yuanzi-atom-templates/examples/com.example.sum`
- **断言**：退出码 0；输出含 `com.example.sum@0.1.0`

## TC-CLI-007 validate 缺少 meta.yaml [P1]

- **准备**：空目录
- **执行**：`yuanzi validate {空目录}`
- **断言**：退出码 1；stderr 含 `meta.yaml not found`

## TC-CLI-008 validate 缺少必需文件 [P1]

- **准备**：复制 com.example.sum，删除 `tests/test_health.py`
- **执行**：`yuanzi validate {目录}`
- **断言**：退出码 1；stderr 含 `missing required files` 与 `tests/test_health.py`

## TC-CLI-009 validate 非法 meta（坏 id） [P1]

- **准备**：目录中写 `meta.yaml`：`id: bad-id` + `version: 0.1`
- **执行**：`yuanzi validate {目录}`
- **断言**：退出码 1；stderr 含 `validation failed`

## TC-CLI-010 validate markdown_rules 类型缺 rules.md [P2]

- **准备**：meta.yaml 使用 `kernel_type: markdown_rules`，不提供 rules.md
- **执行**：`yuanzi validate {目录}`
- **断言**：退出码 1；stderr 含 `rules.md`

## TC-CLI-011 validate meta.yaml 非标量映射（内容为列表） [P2]

- **准备**：meta.yaml 内容为 `- a\n- b`
- **执行**：`yuanzi validate {目录}`
- **断言**：退出码 1；给出可读错误（非 traceback）

## TC-CLI-012 test 命令完整流程 [P0]

- **准备**：com.example.sum 示例
- **执行**：`yuanzi test yuanzi-atom-templates/examples/com.example.sum`
- **断言**：先输出 validate OK，pytest 8 条全过，退出码 0

## TC-CLI-013 test --fast 只跑 kernel 测试 [P1]

- **准备**：com.example.sum 示例
- **执行**：`yuanzi test --fast yuanzi-atom-templates/examples/com.example.sum`
- **断言**：输出含 `(fast mode)`；只执行 5 条 kernel 测试（health 3 条被 -k kernel 跳过）；退出码 0

## TC-CLI-014 test --no-validate 跳过校验 [P2]

- **准备**：com.example.sum 示例
- **执行**：`yuanzi test --no-validate yuanzi-atom-templates/examples/com.example.sum`
- **断言**：不出现 validate 输出；直接跑 pytest；退出码 0

## TC-CLI-015 test 对失败测试返回非零 [P1]

- **准备**：复制 com.example.sum，把 core.py 改为 `1+1=3` 的错误逻辑
- **执行**：`yuanzi test {目录}`
- **断言**：退出码非 0；pytest 报告显示失败

## TC-CLI-016 meta id 校验边界（大写/中文/空格/前导数字） [P2]

- **准备**：直接调用 `yuanzi_cli.meta.validate_meta`
- **执行**：分别校验 id=`COM.EXAMPLE.X`、`com.中文.x`、`com.exa mple.x`
- **断言**（期望）：均应被拒绝或至少文档化；记录实际行为
- **备注**：`str.isalnum()` 对中文返回 True，可能放行非 ASCII id

## TC-CLI-017 meta port 边界校验 [P2]

- **准备**：直接调用 `validate_meta`，port 分别取 0、65536、18777
- **断言**：0 与 65536 拒绝；18777 通过

## TC-CLI-018 init 自定义 template-dir [P2]

- **准备**：`--template-dir yuanzi-atom-templates`
- **执行**：`yuanzi init com.qa.custom -t yuanzi-atom-templates -o {TMP}`
- **断言**：退出码 0，结构与默认一致

## TC-CLI-019 无参数时显示帮助 [P3]

- **执行**：`yuanzi`（不带任何参数）
- **断言**：退出码 0（no_args_is_help）；输出 usage 帮助

## TC-CLI-020 相对路径测试的 CWD 健壮性 [P1]

- **准备**：无
- **执行**：从**仓库根目录**运行 `pytest yuanzi-cli/tests -v`
- **断言**：test_validate.py 中相对路径 `../yuanzi-atom-templates/...` 用例的表现
- **备注**：相对路径依赖 CWD，从根目录运行预期失败 → 记录缺陷
