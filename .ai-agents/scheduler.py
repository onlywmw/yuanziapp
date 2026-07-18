#!/usr/bin/env python3
"""Yuanzi AI Agent Hub — 调度器核心。

从 GitHub Actions 或命令行接收 Issue 事件，检测协作信号，
加载对应角色卡，执行路由动作（标签/指派/评论）。

Usage:
    # GitHub Actions 模式（从环境变量读取事件）
    python .ai-agents/scheduler.py

    # 命令行调试模式
    python .ai-agents/scheduler.py --issue 1 --repo onlywmw/yuanziapp

Requirements:
    - gh CLI 已认证
    - Python 3.10+
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import config directly — no YAML parsing needed
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from config import ROLES, SIGNALS  # noqa: E402

# ============================================================
# GitHub Issue 事件解析
# ============================================================


def get_issue_event() -> Optional[Dict[str, Any]]:
    """Read GitHub Issue event JSON from GITHUB_EVENT_PATH (Actions env)."""
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and Path(event_path).exists():
        raw = Path(event_path).read_text(encoding="utf-8")
        return json.loads(raw)
    return None


def extract_issue_info(event: Dict[str, Any]) -> Dict[str, Any]:
    """Pull standard fields from a GitHub webhook Issue event."""
    issue = event.get("issue", {})
    repo = event.get("repository", {}).get("full_name", "")
    return {
        "repo": repo,
        "issue_number": str(issue.get("number", "")),
        "title": issue.get("title", ""),
        "body": issue.get("body", ""),
        "labels": [lb["name"] for lb in issue.get("labels", [])],
        "action": event.get("action", ""),
        "sender": event.get("sender", {}).get("login", ""),
    }


# ============================================================
# 信号检测
# ============================================================


def detect_signals(issue_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan issue title + body for known collaboration signals (emoji patterns)."""
    text = f"{issue_info['title']}\n{issue_info['body']}"
    matched = []
    for sig in SIGNALS:
        pattern = sig.get("pattern", "")
        if pattern and pattern in text:
            matched.append(sig)
    return matched


# ============================================================
# 动作执行
# ============================================================


def execute_actions(
    signals: List[Dict[str, Any]],
    issue_info: Dict[str, Any],
) -> List[str]:
    """Apply labels + post comment for each matched signal."""
    log: List[str] = []
    repo = issue_info["repo"]
    issue_num = issue_info["issue_number"]

    for sig in signals:
        # --- add label ---
        add_label = sig.get("add_label", "")
        if add_label:
            _gh(
                "label",
                "create",
                add_label,
                "--repo",
                repo,
                "--force",
                silent=True,
            )
            _gh(
                "issue",
                "edit",
                issue_num,
                "--repo",
                repo,
                "--add-label",
                add_label,
            )
            log.append(f"Label +{add_label}")

        # --- remove label ---
        remove_label = sig.get("remove_label", "")
        if isinstance(remove_label, str) and remove_label:
            _gh(
                "issue",
                "edit",
                issue_num,
                "--repo",
                repo,
                "--remove-label",
                remove_label,
            )
            log.append(f"Label -{remove_label}")
        elif isinstance(remove_label, list):
            for rl in remove_label:
                _gh(
                    "issue",
                    "edit",
                    issue_num,
                    "--repo",
                    repo,
                    "--remove-label",
                    str(rl),
                )
                log.append(f"Label -{rl}")

        # --- comment ---
        comment_template = sig.get("comment", "")
        if comment_template:
            rendered = comment_template.format(
                sender=issue_info["sender"],
                issue_title=issue_info["title"],
                issue_number=issue_info["issue_number"],
            )
            _gh_comment(repo, issue_num, rendered)
            log.append("Comment posted")

    return log


# ============================================================
# 角色卡加载
# ============================================================


def load_role_card(role_id: str) -> Optional[str]:
    """Read the .md role file for a given role ID."""
    role = ROLES.get(role_id, {})
    role_file = role.get("role_file", "")
    if not role_file:
        return None
    path = _HERE / role_file
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


# ============================================================
# GitHub CLI helpers
# ============================================================


def _gh(*args: str, silent: bool = False) -> str:
    """Run a gh CLI command, return stdout or '' on failure.

    Uses UTF-8 explicitly to avoid Windows GBK encoding issues.
    """
    cmd = ["gh"] + list(args)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            env=env,
        )
        if result.returncode != 0 and not silent:
            sys.stderr.write(f"[gh] WARN: {' '.join(cmd)} → {result.stderr.strip()}\n")
        return result.stdout.strip()
    except Exception as exc:
        if not silent:
            sys.stderr.write(f"[gh] ERR: {' '.join(cmd)} → {exc}\n")
        return ""


def _gh_comment(repo: str, issue_num: str, body: str) -> str:
    """Post a comment on a GitHub issue via gh CLI (stdin mode)."""
    try:
        result = subprocess.run(
            ["gh", "issue", "comment", issue_num, "--repo", repo, "--body-file", "-"],
            input=body,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if result.returncode != 0:
            sys.stderr.write(f"[gh] WARN: comment failed → {result.stderr.strip()}\n")
        return result.stdout.strip()
    except Exception as exc:
        sys.stderr.write(f"[gh] ERR: comment → {exc}\n")
        return ""


# ============================================================
# 主入口
# ============================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="Yuanzi AI Agent Hub Scheduler")
    parser.add_argument("--issue", help="Issue number (debug mode, overrides event)")
    parser.add_argument("--repo", help="Repository (debug mode)")
    args = parser.parse_args()

    print(f"[scheduler] {len(SIGNALS)} signals configured")

    # ---- Get issue info ----
    if args.issue and args.repo:
        # Debug mode: fetch issue via gh CLI
        issue_info: Dict[str, Any] = {
            "repo": args.repo,
            "issue_number": args.issue,
            "title": "",
            "body": "",
            "labels": [],
            "action": "debug",
            "sender": "cli",
        }
        raw = _gh(
            "issue",
            "view",
            args.issue,
            "--repo",
            args.repo,
            "--json",
            "title,body,labels",
        )
        if raw:
            data = json.loads(raw)
            issue_info["title"] = data.get("title", "")
            issue_info["body"] = data.get("body", "")
            issue_info["labels"] = [lb["name"] for lb in data.get("labels", [])]
        print(f"[scheduler] Debug: #{args.issue} — '{issue_info['title'][:60]}'")
    else:
        event = get_issue_event()
        if not event:
            print("[scheduler] No GitHub event found", file=sys.stderr)
            return 1
        issue_info = extract_issue_info(event)
        print(
            f"[scheduler] Event: {issue_info['action']} "
            f"#{issue_info['issue_number']}"
        )

    # ---- Detect signals ----
    signals = detect_signals(issue_info)
    if not signals:
        print("[scheduler] No signals detected → exit")
        return 0

    print(f"[scheduler] {len(signals)} signal(s) detected:")
    for s in signals:
        print(f"  📡 {s['pattern']} → route to {s.get('route_to', '?')}")

    # ---- Execute ----
    log = execute_actions(signals, issue_info)
    for entry in log:
        print(f"[scheduler] ✓ {entry}")

    print("[scheduler] Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
