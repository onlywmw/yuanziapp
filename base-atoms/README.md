# Yuanzi 基础原子（base-atoms）

> 系统内置原子：**不可注册、不可删除、随系统升级**。
> 接口标准：`/health` `/meta` `/run` | `handler(data)` → `{status, data/message}`

## 14 个基础原子

| 目录 | atom_id | 功能 | 端口 |
|------|---------|------|------|
| file-dir | system.file-dir | 文件夹操作（list/create/delete，沙箱） | 9001 |
| file-read | system.file-read | 文件读取（沙箱白名单，max 5MB） | 9002 |
| file-write | system.file-write | 文件写入（沙箱白名单，max 5MB） | 9003 |
| http-get | system.http-get | HTTP GET（http/https 公网，max 100KB） | 9004 |
| http-post | system.http-post | HTTP POST（同上） | 9005 |
| math-calc | system.math-calc | 数学表达式安全求值（AST，无 eval） | 9006 |
| string-split | system.string-split | 字符串拆分 | 9007 |
| string-match | system.string-match | 正则匹配 | 9008 |
| json-parse | system.json-parse | JSON 解析 | 9009 |
| date-time | system.date-time | 日期时间（now/format/diff） | 9010 |
| hash-digest | system.hash-digest | 哈希（sha256/sha512/md5） | 9011 |
| encrypt-aes | system.encrypt-aes | AES-GCM 加密 | 9012 |
| decrypt-aes | system.decrypt-aes | AES-GCM 解密 | 9013 |
| ai | system.ai | 本地意图理解（规则兜底，可选 ONNX 增强） | 9014 |

## 安全约束

- **文件系原子**：路径必须在白名单根目录内（`ATOM_FILE_ROOTS`，os.pathsep 分隔；
  缺省仅当前工作目录），realpath 前缀检查，拒绝 `..` 穿越
- **HTTP 系原子**：仅 http/https；默认拒绝私网/回环/链路本地地址
  （`ATOM_HTTP_ALLOW_PRIVATE=1` 显式放行）；响应上限 100KB
- **服务层**：默认绑定 127.0.0.1；`YUANZI_TOKEN` 可选鉴权；
  请求体上限 5MB（413）；错误详情默认隐藏（`YUANZI_DEBUG=1` 调试）
- **AES 原子**：key 由入参 `key`（base64）或 `ATOM_AES_KEY` 环境变量提供，永不落盘

## 运行

```bash
cd base-atoms/math-calc
python server.py            # 127.0.0.1:9006
PORT=9106 python server.py  # 自定义端口
```

## 测试

```bash
python -m pytest base-atoms/tests -q
```
