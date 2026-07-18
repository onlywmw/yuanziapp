# 04 - 安全测试用例（OWASP Top 10，权威来源）

**范围**：atoms 示例原子、原子模板 server.py、注册中心、CLI、配置文件
**目标**：OWASP 覆盖率 ≥90%（10 项威胁中验证 9 项以上）

---

## TC-SEC-001 路径穿越：atom-file-read 读取任意文件 [P0 / A01]

- **准备**：调用 `atoms/atom-file-read/core.py` 的 handler
- **执行**：`handler({"path": "C:/Windows/System32/drivers/etc/hosts"})` 及 `handler({"path": "../../../敏感文件"})`
- **断言（期望）**：应被拒绝（沙箱/白名单）
- **备注**：代码中无任何路径限制 → 预期**测试失败** → 提 P0 缺陷

## TC-SEC-002 SSRF：atom-http-get 访问内网/回环 [P0 / A10]

- **准备**：本地回环 HTTP 服务（模拟内网服务）
- **执行**：`handler({"url": "http://127.0.0.1:{PORT}/internal"})`、`handler({"url": "file:///C:/Windows/win.ini"})`
- **断言（期望）**：应被拒绝（协议白名单 + 内网地址过滤）
- **备注**：代码无任何 URL 过滤 → 预期**测试失败** → 提 P0 缺陷

## TC-SEC-003 原子服务绑定 0.0.0.0 且无认证 [P1 / A05+A07]

- **执行**：静态检查 `atoms/*/server.py` 的 `app.run(host=...)` 与鉴权逻辑；检查模板 `server.py` 的 HOST 默认值与 meta.yaml `host: 0.0.0.0`
- **断言（期望）**：默认绑定 127.0.0.1 或有认证
- **备注**：全部 0.0.0.0、无认证 → 提缺陷

## TC-SEC-004 请求体无大小限制（DoS） [P2 / A04]

- **执行**：检查模板 server.py `_read_body`：`int(self.headers.get("Content-Length","0"))` 无上限
- **断言（期望）**：应有最大 body 限制
- **备注**：无限制 → 提缺陷

## TC-SEC-005 注册中心 SQL 注入 [P0 / A03]

- **执行**：`list_atoms(conn, search="' OR '1'='1")`；`category="x' AND 1=1--"`
- **断言**：参数化查询生效，不泄露数据，无异常（与 TC-REG-012 联动）

## TC-SEC-006 YAML 反序列化安全 [P1 / A08]

- **执行**：静态检查 `meta.py load_meta` 与模板 `server.py load_meta` 是否使用 `yaml.safe_load`
- **断言**：全部使用 safe_load（代码审查）

## TC-SEC-007 敏感信息硬编码检查 [P1 / A02+A05]

- **执行**：全仓库 grep 密码/密钥/token 模式；检查 `yuanzi-config.yaml` 中的 adb 个人路径、`device_user`
- **断言**：无真实密钥入库；个人机器路径应抽离为本地配置
- **备注**：adb 路径含用户个人目录 → 提配置卫生缺陷

## TC-SEC-008 错误信息泄露（详细异常回传客户端） [P2 / A05]

- **执行**：模板 server.py `do_POST` 异常时 `{"ok": False, "error": str(exc)}` 原样返回；atoms server.py 同理
- **断言（期望）**：生产模式不应回传内部异常细节
- **备注**：str(exc) 可能泄露路径/内部结构 → 提缺陷

## TC-SEC-009 依赖供应链检查 [P2 / A06]

- **执行**：`pip list` 检查依赖是否钉版本；检查 pyproject 中依赖范围（`>=` 无上限）
- **断言**：记录未锁定依赖 → 建议 lock 文件

## TC-SEC-010 日志安全：审计日志含敏感操作 [P3 / A09]

- **执行**：检查 registry.py `_audit` 是否记录 actor/时间戳（有 → 通过）；检查 atoms 是否无访问日志
- **断言**：注册中心审计合格；atoms 无访问日志 → 记录

---

## OWASP 覆盖映射

| 威胁 | 用例 | 结果 |
|------|------|------|
| A01 访问控制 | TC-SEC-001 | 待执行 |
| A02 加密失败 | TC-SEC-007 | 待执行 |
| A03 注入 | TC-SEC-005 | 待执行 |
| A04 不安全设计 | TC-SEC-004 | 待执行 |
| A05 配置错误 | TC-SEC-003/007/008 | 待执行 |
| A06 脆弱组件 | TC-SEC-009 | 待执行 |
| A07 认证失败 | TC-SEC-003 | 待执行 |
| A08 数据完整性 | TC-SEC-006 | 待执行 |
| A09 日志失败 | TC-SEC-010 | 待执行 |
| A10 SSRF | TC-SEC-002 | 待执行 |
