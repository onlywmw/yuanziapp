# 全量验证方案

> **目的**: 验证整个 Yuanzi 系统——代码、文档、架构一致性
> **范围**: M1-M7 全部阶段
> **执行人**: Audit + Eng + Arch

---

## 验证矩阵

### 第一层：代码质量 (CI 自动化)

```
验证项                      命令                          预期
────────────────────────────────────────────────────────────────
单元测试 277 个             pytest -q                      277 passed
代码格式                   black --check .                0 files would reformat
Lint                      ruff check .                    All checks passed
Pre-commit hooks           pre-commit run --all-files      全部通过
Python 版本兼容             CI matrix (3.10 + 3.12)      双版本通过
```

### 第二层：注册中心功能 (手动+自动化)

```
验证项                      验证方式                      预期
────────────────────────────────────────────────────────────────
原子注册                    POST /atoms                   201, signature 生成
重复注册拒绝                同 content_hash 再注册         409 duplicate_signature
原子审核                    POST /review                  状态: submitted→registered
状态流转                    POST /status                  registered→running→offline
版本快照                    GET /versions                 版本列表正确
版本回滚                    POST /rollback/{v}            恢复到指定版本
依赖解析                    GET /dependencies             order/missing/cycles 正确
健康探针                    POST /probe                   ok, 状态更新, 审计写入
探针安全                    probe file:// URL              拒绝: scheme not allowed
内容去重                    content_hash 落库              物理列非空, 重复注册被拒
审计哈希链                  GET /audit/verify             valid: true
```

### 第三层：原子模型一致性

```
验证项                      对比来源                      预期
────────────────────────────────────────────────────────────────
基础原子 13 个存在           BASE_ATOMS_SPEC vs base-atoms/   13 个目录, 每个有 core.py+server.py
基础原子接口统一             core.handler() 签名              handler(data) → {status, data/message}
基础原子三个端点             /health /meta /run                200 OK, JSON 响应
基础原子不可注册             尝试 POST /atoms system.file-read 拒绝
基础原子不可删除             尝试 DELETE                     拒绝
注册原子有作者                GET /atoms 随机 10 个            ownership.author 非空
注册原子可删除                DELETE /atoms/mcp.xxx           成功
atoms 是 VIEW 不是 TABLE    PRAGMA table_info('atoms')      空 (VIEW 不在 table_info 中)
```

### 第四层：通道模型

```
验证项                      验证方式                      预期
────────────────────────────────────────────────────────────────
通道类型枚举                 5 种类型                        direct/map/transform/merge/split
直通线                      A.output ⊆ B.input             通过
映射线                      body→text 映射                  转换正确
转换线                      number→string 转换              result: "42"
合并线                      多源合并                         字段完整
分流线                      一源分多                         每个目标收到数据
类型不匹配连线                number → url                    验证失败
缺少参数连线                 file-read → encrypt-aes (无key) 验证失败
自循环连线                   A → A                           验证失败
读写循环连线                 file-read → file-write → file-read 验证失败
```

### 第五层：工作流

```
验证项                      验证方式                      预期
────────────────────────────────────────────────────────────────
DAG 无环                    拓扑排序                        成功排序
孤立节点检测                 某节点无输入输出                 验证失败
参数节点                     人工输入 URL/key                正确注入
工作流保存                   POST /workflows                201
工作流执行                   简单 3 节点工作流                 成功, 日志完整
节点失败重试                 故意让某节点失败                   自动重试 3 次
超时终止                     设置 1s 超时                     超时标记
```

### 第六层：安全

```
验证项                      验证方式                      预期
────────────────────────────────────────────────────────────────
无 token 请求                 curl /atoms                    401
错误 token 请求               curl -H "Bearer: bad" /atoms   401
viewer role 读                viewer token GET /atoms        200
viewer role 写                viewer token POST /atoms       403
registry role 注册            registry token POST /atoms     201
admin role 审核               admin token POST /review       200
probe CIDR 限制               probe 内网地址                  拒绝
probe scheme 限制             probe file://                   拒绝
file-read 路径白名单          读白名单外路径                   拒绝
http-get SSRF                请求内网地址                     拒绝
审计哈希链完整性              GET /audit/verify               valid: true
```

### 第七层：文档与架构一致性

```
验证项                      对比来源                        预期
──────────────────────────────────────────────────────────────
接口契约 vs 代码             INTERFACE_CONTRACTS vs registry.py   14 个函数全部匹配
Schema 定义只在一处           migrations/*.sql vs registry.py     registry.py 无 CREATE TABLE
Bug 修复全部闭单              BUG_REGISTRY vs 实际测试             16 个 BUG 全部修复或 M6 覆盖
设计文档不互相矛盾            ARCHITECTURE_OVERVIEW 遍历         无冲突
README 状态匹配实际           README 里程碑 vs 实际 CI             M1-M5 已实现
ADR 决策已被代码遵守           ADR_ATOM_MODEL vs 实际分层          基础原子不可注册
```

---

## 执行顺序

```
Phase 1 — 自动化 (CI, 每次提交)
  277 测试 + black + ruff + pre-commit

Phase 2 — 注册中心 (1h)
  原子 CRUD + 版本 + 依赖 + 探针 + 审计

Phase 3 — 原子模型 (30min)
  基础原子不可删 + 注册原子有作者 + atoms VIEW

Phase 4 — 通道 + 工作流 (2h)
  5 种线 + 类型匹配 + DAG 执行

Phase 5 — 安全 (1h)
  认证 + RBAC + SSRF + 路径沙箱

Phase 6 — 文档审计 (30min)
  契约一致性 + Schema 单一源 + Bug 闭单
```

---

## 验证脚本

```bash
#!/bin/bash
# 全量验证一键脚本
# Usage: bash scripts/verify-all.sh

echo "=== Phase 1: Code Quality ==="
python -m pytest -q && echo "PASS" || echo "FAIL"
black --check . && echo "PASS" || echo "FAIL"
ruff check . && echo "PASS" || echo "FAIL"

echo "=== Phase 2: Registry ==="
python scripts/verify_registry.py

echo "=== Phase 3: Atom Model ==="
python scripts/verify_atom_model.py

echo "=== Phase 4: Channels ==="
python scripts/verify_channels.py

echo "=== Phase 5: Security ==="
python scripts/verify_security.py

echo "=== Phase 6: Docs ==="
python scripts/verify_docs.py
```

---

> **验证不是一次性的。每次合入 main 前都必须跑通 Phase 1，每次发布前跑通全部 6 个 Phase。**
