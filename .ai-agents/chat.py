#!/usr/bin/env python3
"""Yuanzi Agent Chat — 本地多智能体对话室。

5 个角色卡驱动的 AI Agent 在终端里实时对话。
每个 Agent 通过 ``claude -p --system-prompt`` 以各自角色卡作为系统提示运行。

Usage:
    python .ai-agents/chat.py "审查最近的代码提交"
    python .ai-agents/chat.py --rounds 2 "M4 REST API 怎么实现"
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

# UTF-8 stdout for Windows terminal
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from config import ROLES

# ---- locate claude binary ----
import shutil as _shutil
_CLAUDE = "claude"
_found = _shutil.which("claude")
if _found:
    _CLAUDE = _found
else:
    for _c in [
        "C:\\nvm4w\\nodejs\\claude.cmd",
        "C:\\nvm4w\\nodejs\\claude",
        os.path.expandvars(r"%APPDATA%\\npm\\claude.cmd"),
    ]:
        if os.path.isfile(_c):
            _CLAUDE = _c
            break

TIMEOUT = 120  # seconds per agent response

# ---- speaking order ----
ORDER = ["hub", "arch", "eng", "audit", "fixer"]

# ---- ansi ----
C = {
    "hub": "\033[35m", "arch": "\033[34m", "eng": "\033[32m",
    "audit": "\033[33m", "fixer": "\033[31m",
    "reset": "\033[0m", "dim": "\033[90m", "bold": "\033[1m",
}


def load_role(rid: str) -> str:
    path = _HERE / ROLES[rid]["role_file"]
    return path.read_text(encoding="utf-8")


def speak(rid: str, name: str, system: str, context: str) -> str:
    """Run claude -p with role card as system prompt."""
    user_prompt = (
        f"{context}\n\n"
        f"你是 {name}。请用中文简短回复（5-10句话），可以 @其他角色 来协调下一步。"
    )

    try:
        r = subprocess.run(
            [_CLAUDE, "-p", "--system-prompt", system, "--output-format", "text"],
            input=user_prompt,
            capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT,
        )
        if r.returncode != 0:
            return f"❌ {r.stderr.strip()[:200]}"
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return f"⏰ {name} 思考超时 ({TIMEOUT}s)"
    except Exception as e:
        return f"💥 {e}"


def show(rid: str, name: str, text: str) -> None:
    """Display an agent message."""
    color = C.get(rid, "")
    print(f"{color}{C['bold']}[{name} / {rid}]{C['reset']}")
    for line in text.split("\n"):
        print(f"  {line}")
    print(flush=True)


def banner(task: str) -> None:
    print(f"\n{C['bold']}=== Yuanzi Agent Chat ==={C['reset']}")
    print(f"{C['dim']}Hub · Arch · Eng · Audit · Fixer — 5 agents online{C['reset']}")
    print(f"{C['dim']}Task: {task[:80]}{C['reset']}\n", flush=True)


def run(task: str, rounds: int = 2) -> None:
    banner(task)

    # Preload all role cards
    cards: Dict[str, str] = {rid: load_role(rid) for rid in ORDER}

    # Conversation transcript
    log: List[str] = [
        f"## 任务\n{task}\n",
        "## 规则\n"
        "- 发言顺序: Hub → Arch → Eng → Audit → Fixer\n"
        "- 每轮每人发言一次，5-10 句话\n"
        "- 用 @角色名 点名协调\n"
        "- 用中文交流\n"
        "- Hub 总结当前状态并规划下一步\n"
        "- Arch 负责技术方案\n"
        "- Eng 负责代码实现\n"
        "- Audit 检查安全和质量\n"
        "- Fixer 关注 CI 和故障\n",
    ]

    for rnd in range(1, rounds + 1):
        print(f"{C['dim']}--- Round {rnd}/{rounds} ---{C['reset']}\n", flush=True)

        for rid in ORDER:
            name = ROLES[rid]["name"]
            desc = ROLES[rid]["description"]

            # Build context: task + rules + last N messages
            ctx = "\n".join(log)

            print(f"{C['dim']}  {name} 思考中...{C['reset']}", end="\r", flush=True)
            start = time.time()
            reply = speak(rid, name, cards[rid], ctx)
            elapsed = time.time() - start
            print(f"{C['dim']}  {name} ({elapsed:.1f}s){C['reset']}", end="\r", flush=True)

            show(rid, name, reply)
            log.append(f"## {name} ({rid})\n{reply}\n")

        if rnd < rounds:
            time.sleep(0.5)

    print(f"{C['dim']}--- Chat ended ---{C['reset']}\n")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python .ai-agents/chat.py [--rounds N] \"任务描述\"")
        sys.exit(1)

    args = sys.argv[1:]
    rounds = 2
    if args[0] == "--rounds":
        rounds = int(args[1])
        args = args[2:]

    task = " ".join(args)
    run(task, rounds)


if __name__ == "__main__":
    main()
