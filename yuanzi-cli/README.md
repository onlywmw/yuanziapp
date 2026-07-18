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
