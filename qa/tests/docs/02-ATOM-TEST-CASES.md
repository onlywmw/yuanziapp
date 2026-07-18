# 02 - atoms 示例原子 测试用例（权威来源）

**组件**：`atoms/` 下 5 个示例原子（file-read / http-get / math-sum / string-split / template）
**执行方式**：直接调用各原子 `core.py` 的 `handler(data)`（kernel 级）+ 检查 server.py 配置
**说明**：http-get 用本地回环 HTTP 服务作靶机，避免外网依赖。

---

## TC-ATM-001 math-sum 正常加法 [P0]

- **准备**：import atoms/atom-math-sum/core.py
- **执行**：`handler({"a": 10, "b": 20})`
- **断言**：`{"status": "success", "data": {"result": 30.0}}`

## TC-ATM-002 math-sum 缺省参数 [P1]

- **执行**：`handler({})`
- **断言**：success，result == 0.0

## TC-ATM-003 math-sum 非法输入 [P1]

- **执行**：`handler({"a": "abc", "b": 1})`
- **断言**：`status == "error"`，message 非空（不抛未捕获异常）

## TC-ATM-004 math-sum inf/超大数 [P3]

- **执行**：`handler({"a": 1e308, "b": 1e308})`
- **断言**：记录实际行为（result 为 inf 时是否仍返回 success）→ 文档化

## TC-ATM-005 string-split 正常拆分 [P0]

- **执行**：`handler({"text": "a,b,c", "delimiter": ","})`
- **断言**：success，parts == ["a","b","c"]，count == 3

## TC-ATM-006 string-split maxsplit [P1]

- **执行**：`handler({"text": "a,b,c,d", "delimiter": ",", "maxsplit": 2})`
- **断言**：parts == ["a","b","c,d"]，count == 3

## TC-ATM-007 string-split 空分隔符 [P2]

- **执行**：`handler({"text": "abc", "delimiter": ""})`
- **断言**：`status == "error"`（ValueError 被捕获），服务不崩溃

## TC-ATM-008 file-read 读取正常文件 [P0]

- **准备**：临时文件 `hello.txt`，内容 `hi yuanzi`
- **执行**：`handler({"path": "{文件}"})`
- **断言**：success，content == "hi yuanzi"，size 正确

## TC-ATM-009 file-read 文件不存在 [P1]

- **执行**：`handler({"path": "C:/qa/not-exist-12345.txt"})`
- **断言**：`status == "error"`，message 含 `file not found`

## TC-ATM-010 file-read 超 max_size [P1]

- **准备**：100 字节文件；max_size=10
- **执行**：`handler({"path": ..., "max_size": 10})`
- **断言**：error，message 含 `file too large`

## TC-ATM-011 file-read base64 模式 [P1]

- **准备**：二进制文件（0x00-0xFF）
- **执行**：`handler({"path": ..., "mode": "base64"})`
- **断言**：success，content 可 base64 解码还原

## TC-ATM-012 file-read 缺 path 字段 [P1]

- **执行**：`handler({})`
- **断言**：error，message 含 `missing required field: path`

## TC-ATM-013 http-get 正常 GET [P0]

- **准备**：本地 `http.server` 回环服务返回 JSON
- **执行**：`handler({"url": "http://127.0.0.1:{PORT}/data"})`
- **断言**：success，status_code == 200，text 含预期内容

## TC-ATM-014 http-get 缺 url [P1]

- **执行**：`handler({})`
- **断言**：error，message 含 `missing required field: url`

## TC-ATM-015 http-get max_length 截断 [P2]

- **准备**：本地服务返回 5000 字节
- **执行**：`handler({"url": ..., "max_length": 100})`
- **断言**：返回 text 长度 == 100

## TC-ATM-016 http-get 无效 URL 容错 [P1]

- **执行**：`handler({"url": "not-a-url"})`
- **断言**：`status == "error"`，无未捕获异常

## TC-ATM-017 示例原子端口冲突检查 [P1]

- **准备**：查看 5 个 atoms/*/server.py 的 `app.run(port=...)`
- **执行**：静态检查各端口值
- **断言**：若全部硬编码 8080，则同时启动必然冲突 → 记录缺陷（应从 meta/环境读取端口）

## TC-ATM-018 atoms 与模板 meta id 规范一致性 [P2]

- **准备**：atoms/*/server.py 中 `/meta` 的 id（如 `atom.file.read`）vs CLI 校验的反向域名规范（`com.example.sum`）
- **执行**：对比两处 id 格式
- **断言**：记录不一致 → 生态规范应统一
