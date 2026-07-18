# 工作流连线规则

> **性质**: 原子编排约束 — 定义原子间数据流的有效/无效/危险连接
> **原则**: 类型匹配、逻辑合理、防止副作用

---

## 一、原子输入输出类型

每个基础原子有明确的输入和输出类型：

| 原子 | 输入 (需要什么) | 输出 (产生什么) |
|------|----------------|----------------|
| file-dir | path, (action) | entries[] |
| file-read | path | content: string |
| file-write | path, content | written: int |
| http-get | url: string, (headers) | body: string, status_code: int |
| http-post | url: string, body: string | body: string, status_code: int |
| math-calc | expression: string | result: number |
| string-split | text: string, delimiter: string | parts[]: string |
| string-match | text: string, pattern: string | matches[]: string |
| json-parse | text: string | data: object |
| date-time | (action, format) | result: string |
| hash-digest | text: string, algorithm | digest: string |
| encrypt-aes | text: string, key: string | ciphertext: string, iv: string |
| decrypt-aes | ciphertext: string, key: string, iv: string | text: string |

---

## 二、连线规则

### 规则 1：类型必须匹配

```
前置原子的输出字段 → 必须覆盖后置原子的必填输入字段

✅ http-get.body ──→ json-parse.text     (string → string, 匹配)
✅ json-parse.data ──→ string-split.text  (object → 取其中字段转 string)
❌ math-calc.result ──→ http-get.url       (number → 不是 string)
❌ file-read.content ──→ math-calc         (string → 需要 expression, 不是任意 string)
```

### 规则 2：缺失必填参数 → 无效连线

```
前置原子: file-read → 输出 {content: "hello world"}

后置原子: encrypt-aes → 需要 {text: string, key: string, iv?: string}

连线: file-read → encrypt-aes
  file-read 提供了 text ✅
  但 key 来自哪里？❌

→ 无效连线。缺少 key 参数。
→ 需要插入一个人工确认或密钥管理原子来提供 key。
```

### 规则 3：自循环 → 禁止

```
❌ file-write ──→ file-write        (无限写)
❌ http-get ──→ http-get            (无限请求)
❌ math-calc ──→ math-calc          (无限计算)
```

### 规则 4：无意义链 → 警告

```
⚠️ string-split ──→ string-split    (拆了又拆, 不报错但无意义)
⚠️ hash-digest ──→ hash-digest      (哈希的哈希, 极少场景需要)
⚠️ json-parse ──→ json-parse        (解析两次, 除非输出是 JSON 字符串)
```

### 规则 5：写操作不能成环

```
❌ file-read ──→ file-write ──→ file-read
     ↑                           │
     └───────────────────────────┘
     
→ 读写循环：读了写、写了读、无限循环 → 磁盘 IO 打满
```

---

## 三、有效连线速查

```
典型工作流模式:

1. 数据获取 + 处理:
   http-get ──→ json-parse ──→ string-split ──→ math-calc

2. 文件读取 + 加密存储:
   file-read ──→ encrypt-aes ──→ file-write
                   ↑
              (key 来自系统配置)

3. 配置解析 + HTTP 请求:
   file-read ──→ json-parse ──→ http-post
   (读配置文件)  (解析JSON)    (POST 到 API)

4. 文本处理:
   string-split ──→ string-match ──→ hash-digest

5. 时间 + 写入:
   date-time ──→ file-write
   (获取时间戳)  (写入日志)
```

---

## 四、无效连线速查

```
❌ math-calc ──→ http-get          (数字不是 URL)
❌ date-time ──→ encrypt-aes       (缺 key)
❌ file-read ──→ encrypt-aes       (缺 key)
❌ file-write ──→ http-get         (写入结果不是 URL)
❌ hash-digest ──→ http-get        (哈希值不是 URL)
❌ http-get ──→ file-dir           (响应体不是路径)
❌ string-split ──→ file-read      (字符串不是文件路径)
❌ json-parse ──→ decrypt-aes      (缺 key 和 iv)
```

---

## 五、原子分类：管线角色

根据在管线中的位置，原子分三类：

| 角色 | 特征 | 示例 |
|------|------|------|
| **源** | 不需要前置原子，自产生数据 | date-time, file-dir |
| **处理** | 有输入有输出，可串联 | json-parse, string-split, math-calc, encrypt-aes |
| **汇** | 输出为最终结果，通常不再传递 | file-write, http-post |

```
源 ──→ 处理 ──→ 处理 ──→ 汇

date-time ──→ string-match ──→ json-parse ──→ file-write
 (源)         (处理)           (处理)        (汇)
```

---

## 六、连线验证流程

注册原子声明工作流时，系统自动检查：

```
1. 每个连线检查输出→输入类型匹配
2. 必填参数是否被前置原子覆盖
3. 是否有自循环
4. 是否有读写循环
5. 是否缺少参数（标记为"需人工提供"）

验证通过 → 工作流可执行
验证失败 → 返回具体错误，包含"哪个原子→哪个原子，缺少什么"
```

---

> **工作流连线规则让原子编排从"随便试"变成"一次对"。**
> **前提: 每个原子必须在 /meta 端点中声明自己的输入/输出 schema。**
