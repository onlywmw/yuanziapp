"""Append code-review findings (689ad4e probing + related commits) to QA trackers."""
from __future__ import annotations

import csv
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "docs" / "templates"
TRACK = BASE / "TEST-EXECUTION-TRACKING.csv"
BUGS = BASE / "BUG-TRACKING-TEMPLATE.csv"
DATE = "2026-07-18"
WHO = "Kimi-QA(Review)"
ENV = "OS: Windows 11\nPython: 3.12.13\nRepo: main@689ad4e"

REVIEW_ROWS = [
    ("TC-REV-001", "Review", "P1", "分层签名下能力克隆仍可注册", "3", "内存 DB", "Completed", "❌ FAILED", "BUG-016", DATE, WHO, "com.qa.beta 与 alpha 同能力不同 id 仍 success；content_hash 未持久化（无列、行内无），去重不可执行也不可查询", ""),
    ("TC-REV-002", "Review", "P1", "probe file:// scheme 崩溃", "2", "health_url=file:///...", "Completed", "❌ FAILED", "BUG-014", DATE, WHO, "TypeError: '<=' not supported between 'int' and 'NoneType'；批量探测会被单行数据整体搞死", ""),
    ("TC-REV-003", "Review", "P2", "probe ftp:// scheme 容错", "2", "", "Completed", "✅ PASSED", "", DATE, WHO, "http_503 -> unreachable，未崩溃（环境代理相关，行为可接受）", ""),
    ("TC-REV-004", "Review", "P2", "no_endpoint/not_found 审计缺口", "2", "", "Completed", "❌ FAILED", "BUG-018", DATE, WHO, "no_endpoint 分支无 probe 审计记录，与'每次探测记审计日志'声明不符", ""),
    ("TC-REV-005", "Review", "P2", "offline 探测失败的状态机一致性", "2", "offline 原子探死端口", "Completed", "❌ FAILED", "BUG-019", DATE, WHO, "offline->unreachable 实际发生但不在 set_atom_status 流转表；probe 绕过状态机校验，双路径并存", ""),
    ("TC-REV-006", "Review", "P2", "rejected 原子只记录不改状态", "2", "", "Completed", "✅ PASSED", "", DATE, WHO, "rejected 保持，runtime 记录 connection_error，probe 审计已写（符合设计）", ""),
    ("TC-REV-007", "Review", "P1", "install-hooks 无界向上搜索副作用", "5", "home 存在配置+home 是 git 仓库", "Completed", "❌ FAILED", "BUG-015", DATE, WHO, "test_install_hooks_no_config 本机失败（exit 0≠1）；真实 pip install + 钩子植入 home 仓库；环境依赖测试", ""),
    ("TC-REV-008", "Review", "P2", "bridge+CLI 测试复跑", "5", "venv", "Completed", "❌ FAILED", "BUG-015", DATE, WHO, "bridge 31/31 通过；CLI 8/9 通过（test_install_hooks_no_config 环境依赖失败）；'累计40 passed' 在本机不成立", ""),
    ("TC-REV-009", "Review", "P2", "probing 状态是否被实际设置", "1", "全仓 grep", "Completed", "❌ FAILED", "BUG-017", DATE, WHO, "probing 仅出现在流转表/_PROBEABLE_STATUSES，无任何代码路径设置该状态 → 死状态", ""),
]

NEW_BUGS = [
    ("BUG-014", "probe_atom 遇 file:// 等非 HTTP scheme 崩溃（TypeError），批量探测整体中断", "P1", "mcp-yuanzi-bridge / registry.probe_atom",
     "TC-REV-002", "Open", DATE, WHO, "注册中心维护者",
     "urllib 对 file:// 返回的响应对象 status 为 None，代码执行 200 <= code < 300 抛 TypeError。probe_atoms 批量列表推导未做隔离，一行坏数据导致整个批量探测崩溃。同时非 http(s) scheme 本身就不应被允许探测。",
     "1. 注册 atom 且 runtime.health_url='file:///C:/Windows/win.ini'\n2. probe_atom(conn, id)",
     "校验 scheme 仅允许 http/https；非法 scheme 归为 probe_status='invalid_url' 并正常落库",
     "TypeError 未处理异常；批量 CLI 整体失败",
     ENV, "", "urlopen 前校验 scheme；批量循环内捕获单原子异常", "", "", ""),
    ("BUG-015", "install-hooks 向上搜索无边界 + 负路径测试未 stub，产生真实本机副作用", "P1", "yuanzi-cli / install-hooks + 测试",
     "TC-REV-007", "Open", DATE, WHO, "CLI 维护者",
     "_find_repo_root 从起点一直向上搜到文件系统根。本机 home 目录恰有 .pre-commit-config.yaml 且 home 是 git 仓库：test_install_hooks_no_config 未 stub subprocess，于是真实执行 pip install pre-commit 并把钩子安装进 home 仓库。测试在作者机通过（祖先无配置），属环境依赖；命令本身会把钩子装进完全不相关的仓库。",
     "1. 在祖先含 .pre-commit-config.yaml 的机器上跑 pytest yuanzi-cli/tests\n2. 观察 test_install_hooks_no_config",
     "向上搜索应在遇到 .git 边界/用户 home 时停止；负路径测试必须 stub subprocess",
     "测试 exit=0≠1；钩子被植入 C:/Users/Administrator/.git/hooks；pre-commit 被装入当前环境",
     ENV, "", "搜索遇 .git 即停（或不越过 repo 边界）；测试补 stub；建议增加 --dry-run", "", "", ""),
    ("BUG-016", "content_hash/identity_hash 不持久化，能力去重仍不可执行（BUG-006 未闭环）", "P1", "mcp-yuanzi-bridge / registry",
     "TC-REV-001", "Open", DATE, WHO, "注册中心维护者",
     "9cb0fa6 让 compute_signature 去掉 atom_id，0710a3d 改为 content+identity 双层并重新把 atom_id 经 identity_hash 纳入主签名——两提交意图互相矛盾。实测：同能力不同 atom_id 的原子仍注册成功；content_hash 只写入内存中的 atom dict，不落库（无列、JSON 列中亦无），提交后无法按能力查重。",
     "1. submit atom A(functions=[f1])\n2. submit atom B(同能力, 不同 atom_id)",
     "B 被拒绝（或至少标记 duplicate_content 警告）；content_hash 应持久化并可查询",
     "B success；DB 中无 content_hash 痕迹",
     ENV, "", "signature_hash 改用 content_hash 作主去重键，或新增 content_hash 列+唯一/警告逻辑；明确两提交的最终语义", "", "", ""),
    ("BUG-017", "probing 状态为死代码：无任何路径设置该状态", "P2", "mcp-yuanzi-bridge / registry.probe_atom",
     "TC-REV-009", "Open", DATE, WHO, "注册中心维护者",
     "schema 枚举、set_atom_status 流转表、_PROBEABLE_STATUSES 都包含 probing，但 probe_atom 同步执行，直接把状态置为 running/unreachable，从不设置 probing。声明的状态机与实际行为不一致。",
     "1. grep probing mcp-yuanzi-bridge/registry.py",
     "探测开始时先置 probing（两阶段写入，崩溃可识别），或从枚举/流转中移除",
     "probing 永远不会出现",
     ENV, "", "二选一：两阶段写入 probing；或删除该状态", "", "", ""),
    ("BUG-018", "probe 的 not_found/no_endpoint 分支不写审计，与提交说明不符", "P2", "mcp-yuanzi-bridge / registry.probe_atom",
     "TC-REV-004", "Open", DATE, WHO, "注册中心维护者",
     "commit 声明'每次探测记审计日志'，但 not_found 与 no_endpoint 直接 return，无 audit、runtime_json 也无探测痕迹。无端点的原子会永远停在 registered 且无任何记录。",
     "1. 注册 runtime={} 的原子并 review 通过\n2. probe_atom 后查 get_audit_log",
     "no_endpoint 也应记一条 probe 审计（detail=no_endpoint），便于运营发现配置缺失",
     "audit 只有 submit/review，无 probe",
     ENV, "", "两个早退分支补 _audit", "", "", ""),
    ("BUG-019", "生命周期存在双写入路径，状态机规则不一致", "P2", "mcp-yuanzi-bridge / registry",
     "TC-REV-005", "Open", DATE, WHO, "注册中心维护者",
     "probe_atom 直接改写 lifecycle_json，绕过 set_atom_status 的流转校验。实测发生 offline→unreachable，但该转换不在 allowed_transitions 表中。规则漂移：文档（流转表）与实际（probe 行为）两个事实来源。",
     "1. 原子置 offline\n2. probe 死端口\n3. 状态变 unreachable",
     "probe 复用 set_atom_status（或抽取统一校验函数），流转表补 offline→unreachable",
     "probe 做了流转表不允许的转换",
     ENV, "", "probe 内部调用 set_atom_status；同步更新流转表与注释", "", "", ""),
    ("BUG-020", "probe 对注册表中的任意 URL 发起请求，无 scheme/地址校验（信任边界）", "P2", "mcp-yuanzi-bridge / registry.probe_atom",
     "TC-SEC-002", "Open", DATE, WHO, "注册中心维护者",
     "health_url 来自注册数据（可能由批量导入等不可信来源写入）。批量探测会对这些 URL 发起真实请求，等价于内网扫描（与 BUG-008 同类 SSRF 面）。至少应限定 http/https 并文档化信任假设；对私网地址探测应显式开关。",
     "1. 在 runtime.health_url 写入内网地址\n2. 运行 probe_atoms",
     "scheme 白名单 http/https；文档说明注册数据信任边界；可选禁止私网地址",
     "任意 URL 都会被请求",
     ENV, "", "同 BUG-014 的 scheme 校验一并实现", "", "", ""),
    ("BUG-021", "probe_atoms CLI 永远 exit 0、串行执行、--json 无汇总，不可用于监控", "P2", "mcp-yuanzi-bridge / probe_atoms.py",
     "TC-REV-008", "Open", DATE, WHO, "注册中心维护者",
     "1) main 无条件 return 0，存在 unreachable 时也无法被 cron/监控判失败；2) 串行探测，61 个原子×2s 超时最坏约 2 分钟；3) --json 只有结果数组，无 N/M 汇总字段。",
     "1. probe_atoms.py --json（含 down 原子）\n2. echo $?",
     "提供 --fail-on-unreachable（或默认非零）；ThreadPoolExecutor 并发；json 增加 summary",
     "exit 恒 0；串行；无 summary",
     ENV, "", "见描述", "", "", ""),
    ("BUG-022", "高频探测将刷爆审计表", "P3", "mcp-yuanzi-bridge / registry.probe_atom",
     "TC-REV-006", "Open", DATE, WHO, "注册中心维护者",
     "每次探测写一条 audit。定时探测（如 5 分钟×61 原子）每天产生约 1.7 万条审计，atom_audit_log 将迅速膨胀，真正重要的状态变更被淹没。",
     "1. 对同一原子连续 probe 多次\n2. get_audit_log 每条都落",
     "仅在状态变化时记审计（或按时间节流）；结果不变只更新 runtime_json",
     "每次探测一条 audit",
     ENV, "", "状态不变时省略 audit 或降级为计数", "", "", ""),
]


def main():
    with open(TRACK, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    ids = {r[0] for r in rows[1:] if r}
    body = rows[1:] + [list(r) for r in REVIEW_ROWS if r[0] not in ids]
    with open(TRACK, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(rows[0])
        w.writerows(body)

    with open(BUGS, newline="", encoding="utf-8") as f:
        brows = list(csv.reader(f))
    bids = {r[0] for r in brows[1:] if r}
    bbody = brows[1:] + [list(b) for b in NEW_BUGS if b[0] not in bids]
    with open(BUGS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(brows[0])
        w.writerows(bbody)

    print(f"tracking rows: {len(body)} (+{len(body) - len(rows) + 1})")
    print(f"bug rows: {len(bbody)} (+{len(bbody) - len(brows) + 1})")


if __name__ == "__main__":
    main()
