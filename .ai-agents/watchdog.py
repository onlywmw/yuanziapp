#!/usr/bin/env python3
"""Yuanzi Agent Watchdog — 本地守护进程。

每秒轮询 GitHub Issues，发现新信号立即在本地终端报出，让你看到团队在干活。

Usage:
    python .ai-agents/watchdog.py
    python .ai-agents/watchdog.py --interval 5   # 5 秒轮询一次

Ctrl+C 停止。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Force UTF-8 to avoid Windows GBK emoji crashes
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from config import SIGNALS

# Locate gh.exe — not always in PATH on Windows
_GH = "gh"
_GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
import shutil as _shutil
_found = _shutil.which("gh")
if not _found:
    for _c in [
        os.path.expandvars(r"%LOCALAPPDATA%\bin\gh.exe"),
        os.path.expandvars(r"%APPDATA%\bin\gh.exe"),
    ]:
        if os.path.isfile(_c):
            _GH = _c
            break
else:
    _GH = _found

# Get token once at startup
if not _GH_TOKEN:
    try:
        _result = subprocess.run(
            [_GH, "auth", "token"],
            capture_output=True, text=True, encoding="utf-8", timeout=5
        )
        if _result.returncode == 0:
            _GH_TOKEN = _result.stdout.strip()
    except Exception:
        pass

_GH_ENV = {**os.environ, "GH_TOKEN": _GH_TOKEN, "GITHUB_TOKEN": _GH_TOKEN}


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def color(text: str, code: int) -> str:
    """Simple ANSI color wrapper (works in modern Windows Terminal)."""
    return f"\033[{code}m{text}\033[0m"


def _gh_json(*args: str) -> Any:
    """Run gh CLI with --json and parse result."""
    cmd = [_GH] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            env=_GH_ENV,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception:
        return None


def fetch_recent_issues(repo: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent issues with their labels and last comments."""
    return _gh_json(
        "issue", "list",
        "--repo", repo,
        "--state", "open",
        "--limit", str(limit),
        "--json", "number,title,labels,updatedAt,comments",
    ) or []


def fetch_issue_detail(repo: str, number: int) -> Dict[str, Any]:
    """Get full issue detail including body and comments."""
    data = _gh_json(
        "issue", "view", str(number),
        "--repo", repo,
        "--json", "number,title,body,labels,comments,createdAt,updatedAt",
    )
    return data or {}


def scan_for_signals(issue: Dict[str, Any]) -> List[str]:
    """Check if an issue title/body/comments contain agent signals."""
    text = issue.get("title", "") + "\n" + issue.get("body", "")
    # issue.comments may be a list of objects or an integer count
    for comment in (issue.get("comments") or []):
        if isinstance(comment, dict):
            text += "\n" + comment.get("body", "")

    found = []
    for sig in SIGNALS:
        if sig["pattern"] in text:
            found.append(sig["pattern"])
    return found


def _safe(text: str) -> str:
    """Strip emoji and non-ASCII from text for Windows terminal safety."""
    try:
        return text.encode("ascii", errors="replace").decode("ascii")
    except Exception:
        return str(text)


def _print(*args: str, **kwargs: Any) -> None:
    """Print that survives Windows GBK emoji crashes."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = tuple(_safe(str(a)) for a in args)
        print(*safe_args, **kwargs)


def render_issue_card(issue: Dict[str, Any], signals: List[str]) -> None:
    """Print a compact issue card to the terminal."""
    num = issue["number"]
    title = _safe(issue["title"][:70])
    labels = [_safe(lb["name"]) for lb in issue.get("labels", [])]

    label_str = " ".join(f"[{lb}]" for lb in labels) if labels else color("[no labels]", 90)

    for sig_entry in SIGNALS:
        sig = sig_entry["pattern"]
        if sig not in signals:
            continue
        role = sig_entry["route_to"]
        desc = sig_entry["description"]
        # Use description instead of emoji to avoid Windows GBK issues
        print(f"  [{desc}] → {color(role, 96)}", end="  ")

    print(f"#{num} {color(title, 97)}  {label_str}")

    # Show latest comment if available
    comments = issue.get("comments") or []
    if comments and isinstance(comments, list) and len(comments) > 0:
        last = comments[-1]
        if isinstance(last, dict):
            author = _safe(str(last.get("author", {}).get("login", "?")))
            body = _safe(last.get("body", "")[:100].replace("\n", " "))
            print(f"    @{author}: {body}")
    elif isinstance(comments, int) and comments > 0:
        print(f"    {color(f'({comments} comments)', 90)}")


def main() -> None:
    repo = os.environ.get("YUANZI_REPO", "onlywmw/yuanziapp")
    interval = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3

    # Startup self-check
    try:
        result = subprocess.run(
            [_GH, "--version"], capture_output=True, text=True,
            encoding="utf-8", timeout=5
        )
        if result.returncode != 0:
            print(f"ERROR: gh CLI not working — {result.stderr.strip()}")
            return
    except Exception as e:
        print(f"ERROR: gh CLI check failed — {e}")
        return

    print("+----------------------------------+")
    print("|  Yuanzi Agent Team - Live Feed  |")
    print("+----------------------------------+")
    print(f"  Repository: {repo}")
    print(f"  Polling:    every {interval}s")
    print(f"  Started:    {ts()}")
    print(f"  Ctrl+C to stop")
    print()

    seen_updates: Dict[int, str] = {}  # issue_number → last updatedAt
    first_scan = True

    try:
        while True:
            if first_scan:
                print(f"[{ts()}] Scanning GitHub Issues...", end="", flush=True)

            issues = fetch_recent_issues(repo)

            if first_scan:
                print(f"\r[{ts()}] Found {len(issues)} open issue(s)      ")
                first_scan = False

            if issues is None:
                print(f"\r[{ts()}] ERROR: Failed to fetch issues — retrying...", end="")
                time.sleep(interval)
                continue

            new_activity = False
            for issue in issues:
                num = issue["number"]
                updated = issue.get("updatedAt", "")

                # First scan: fetch full detail for signal detection
                if num not in seen_updates:
                    seen_updates[num] = updated
                    detail = fetch_issue_detail(repo, num)
                    signals = scan_for_signals(detail) if detail else []
                    if signals:
                        new_activity = True
                        print(f"[{ts()}] {color('NEW', 92)}", end=" ")
                        render_issue_card(detail, signals)
                    continue

                # Subsequent scans: report changes
                if updated != seen_updates[num]:
                    seen_updates[num] = updated
                    detail = fetch_issue_detail(repo, num)
                    signals = scan_for_signals(detail) if detail else []
                    if signals:
                        new_activity = True
                        print(f"[{ts()}] {color('UPD', 93)}", end=" ")
                        render_issue_card(detail, signals)

            if not new_activity:
                print(f"\r[{ts()}] {color('idle — waiting for signals...', 90)}", end="")
            else:
                print()  # newline after activity block

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n[{ts()}] {color('Watchdog stopped.', 90)}")
        print(f"  View live: https://github.com/{repo}/issues")


if __name__ == "__main__":
    main()
