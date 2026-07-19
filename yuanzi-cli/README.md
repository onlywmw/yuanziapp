# yuanzi-cli

Yuanzi 原子生态的命令行开发工具。

## 安装

```bash
cd yuanzi-cli
python -m pip install -e .
```

安装后可以使用全局命令：

```bash
yuanzi --version
```

## 命令

### `yuanzi atom init <atom-id>`

按原子基座 v2.1 §7 创建新原子：固定排序 7 个文件，所有原子一致。

```
<atom-id>/
├── core.py              ← handler(data) 模板
├── meta.json            ← I/O schema 空白模板（含 side_effect，默认 impure）
├── server.py            ← /health /meta /run 标准端点（加固骨架）
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_smoke.py
    └── test_contract.py
```

```bash
yuanzi atom init com.example.weather-sensor
```

- atom id 必须为反向域名风格（如 `com.example.weather-sensor`），非法 id 直接拒绝
- 目标目录已存在时给出友好错误，不覆盖
- 生成的 `server.py` 默认绑定 `127.0.0.1`，5MB body 上限，支持 `YUANZI_TOKEN` 鉴权
- 生成物开箱可测：进入原子目录执行 `python -m pytest` 即可通过

选项：

- `--output-dir, -o`：输出目录（默认当前目录）

### `yuanzi init [atom-id]`

从官方 Cookiecutter 模板创建一个新原子。

```bash
# 交互式创建
yuanzi init

# 指定 atom id 快速创建
yuanzi init com.example.my-atom
```

选项：

- `--template-dir, -t`：自定义模板目录
- `--output-dir, -o`：输出目录（默认当前目录）

### `yuanzi validate [path]`

校验原子的 `meta.yaml` 和目录结构。

```bash
# 校验当前目录
yuanzi validate

# 校验指定原子
yuanzi validate /path/to/com.example.my-atom
```

### `yuanzi test [path]`

运行原子的 pytest 测试套件，默认先执行 `yuanzi validate`。

```bash
# 测试当前目录
yuanzi test

# 跳过校验
yuanzi test --no-validate

# 透传 pytest 参数
yuanzi test -- -v -k kernel
```

### `yuanzi install-hooks [path]`

为仓库安装 pre-commit 钩子。从 `path` 向上查找 `.pre-commit-config.yaml`，
安装 pre-commit 包并注册 git 钩子。

```bash
# 在仓库内任意目录执行
yuanzi install-hooks
```

## 开发

```bash
python -m pip install -e ".[dev]"
python -m pytest
```
