# 基础原子规格书

> **性质**: 系统内置原子定义 — 不可注册、不可删除、随系统升级
> **接口标准**: `/health` `/meta` `/run` | `handler(data)` → `{status, data/message}`
> **作者**: system（内置）

---

## 13 个基础原子

### 系统级 (5 个)

#### 1. file-dir — 文件夹操作

```
atom_id:    system.file-dir
输入:       {"action": "list"|"create"|"delete", "path": "/data/...", "recursive": false}
输出:       {"entries": [{"name": "...", "type": "file"|"dir", "size": 1024}]}
```

#### 2. file-read — 文件读取

```
atom_id:    system.file-read
输入:       {"path": "/data/...", "mode": "text"|"base64", "encoding": "utf-8"}
输出:       {"content": "...", "size": 1024}
约束:       路径限于白名单目录；max 5MB
```

#### 3. file-write — 文件写入

```
atom_id:    system.file-write
输入:       {"path": "/data/...", "content": "...", "mode": "text"|"base64", "append": false}
输出:       {"written": 1024, "path": "/data/..."}
约束:       路径限于白名单目录；max 5MB
```

#### 4. http-get — HTTP GET 请求

```
atom_id:    system.http-get
输入:       {"url": "https://...", "headers": {}, "timeout": 30}
输出:       {"status_code": 200, "headers": {}, "body": "..."}
约束:       scheme 白名单 (http/https)；无内网 IP；max 100KB；timeout 30s
```

#### 5. http-post — HTTP POST 请求

```
atom_id:    system.http-post
输入:       {"url": "https://...", "headers": {}, "body": "...", "timeout": 30}
输出:       {"status_code": 200, "headers": {}, "body": "..."}
约束:       同 http-get
```

### 计算级 (5 个)

#### 6. math-calc — 数学运算

```
atom_id:    system.math-calc
输入:       {"expression": "2 + 3 * 4", "precision": 2}
输出:       {"result": 14.0}
```

#### 7. string-split — 字符串拆分

```
atom_id:    system.string-split
输入:       {"text": "a,b,c", "delimiter": ",", "maxsplit": -1}
输出:       {"parts": ["a", "b", "c"], "count": 3}
```

#### 8. string-match — 正则匹配

```
atom_id:    system.string-match
输入:       {"text": "hello world", "pattern": "\\w+", "flags": "g"}
输出:       {"matches": ["hello", "world"], "count": 2}
```

#### 9. json-parse — JSON 解析

```
atom_id:    system.json-parse
输入:       {"text": "{\"key\": \"value\"}"}
输出:       {"data": {"key": "value"}}
```

#### 10. date-time — 日期时间处理

```
atom_id:    system.date-time
输入:       {"action": "now"|"format"|"diff", "value": "...", "format": "ISO8601", "timezone": "UTC"}
输出:       {"result": "2026-07-18T14:00:00Z"}
```

### 安全级 (3 个)

#### 11. hash-digest — 哈希计算

```
atom_id:    system.hash-digest
输入:       {"text": "...", "algorithm": "sha256"|"sha512"|"md5"}
输出:       {"digest": "e3b0c442...", "algorithm": "sha256"}
```

#### 12. encrypt-aes — AES 加密

```
atom_id:    system.encrypt-aes
输入:       {"text": "...", "key": "...", "mode": "CBC"|"GCM"}
输出:       {"ciphertext": "...", "iv": "...", "mode": "CBC"}
```

#### 13. decrypt-aes — AES 解密

```
atom_id:    system.decrypt-aes
输入:       {"ciphertext": "...", "key": "...", "iv": "...", "mode": "CBC"|"GCM"}
输出:       {"text": "..."}
```

---

## 目录结构标准

```
base-atoms/
├── file-dir/
│   ├── core.py           ← handler(data) 唯一业务逻辑
│   ├── server.py         ← 三个端点 (/health /meta /run)
│   ├── requirements.txt  ← 空或最小依赖
│   └── Dockerfile        ← 标准模板
├── file-read/
│   └── ...
├── ... (13 个)
└── README.md
```

---

## 与旧原子的映射

| 旧 atoms/ | 新 base-atoms/ | 变化 |
|-----------|---------------|------|
| atom-math-sum | math-calc | 扩展为表达式计算 |
| atom-string-split | string-split | 保持一致 |
| atom-file-read | file-read | 保持一致 |
| atom-http-get | http-get | 保持一致 |
| atom-template | (删除) | 模板不是原子 |

---

## 删除清单

```
旧文件:
  atoms/atom-math-sum/
  atoms/atom-string-split/
  atoms/atom-file-read/
  atoms/atom-http-get/
  atoms/atom-template/
  atoms/tests/test_example_atoms.py
  atoms/tests/conftest.py
  atoms/tests/__init__.py
  atoms/README.md
```
