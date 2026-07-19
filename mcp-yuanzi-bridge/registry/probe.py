"""健康探测：scheme 白名单、CIDR 限制、DNS 钉扎、乐观锁重试。

由 registry.py 拆分而来（ISOLATION_HARDENING_PLAN 加固1），纯结构移动，逻辑零变化。
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import ipaddress
import json
import logging
import os
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .audit import _audit
from .core import _transition_allowed, get_atom, list_atoms
from .schema import REGISTRY_TABLE, ConcurrentModificationError, now_iso


# 探测后允许变更生命周期的状态；deprecated / rejected 只记录探测结果，不改状态
_PROBEABLE_STATUSES = {"registered", "probing", "running", "unreachable", "offline"}

# 只允许探测 http/https（BUG-014/020）：注册数据不可信，其他 scheme
# （file:// 等）既不合法也会让 urllib 返回非 HTTP 响应导致崩溃。
_ALLOWED_PROBE_SCHEMES = {"http", "https"}

# M6.5b / 裁决 2026-07-18-01：probe 目标地址默认仅允许回环，
# 可用 YUANZI_PROBE_ALLOWED_CIDR 追加网段（逗号分隔），
# 例如 "127.0.0.0/8,192.168.1.0/24"。
_DEFAULT_PROBE_CIDRS = "127.0.0.0/8,::1/128"


def _allowed_probe_networks() -> List[Any]:
    raw = os.environ.get("YUANZI_PROBE_ALLOWED_CIDR", _DEFAULT_PROBE_CIDRS)
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item))
        except ValueError:
            # BUG-033：畸形项跳过并告警，不让一条脏配置拖垮整个 probe
            logging.warning(
                "Ignoring malformed YUANZI_PROBE_ALLOWED_CIDR entry: %r", item
            )
    return networks


def _resolve_host(host: str, timeout: float) -> List[Any]:
    """带时限的 getaddrinfo（BUG-033）。

    系统 DNS 解析自身没有超时，可能阻塞数十秒，probe 的 timeout 管不到
    这一层。用单线程池执行并限时等待；超时后不再 join 工作线程——
    getaddrinfo 不可中断，线程会泄漏到解析结束才回收，代价已接受。
    """
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(socket.getaddrinfo, host, None)
    try:
        return future.result(timeout=timeout)
    finally:
        pool.shutdown(wait=False)


def _probe_address_error(url: str, timeout: float) -> Tuple[Optional[str], List[Any]]:
    """检查探测目标地址是否在允许网段内。

    返回 (错误信息, 已验证的解析结果)；错误信息为 None 表示允许。
    解析结果供调用方做 DNS 钉扎（BUG-033 防重绑定 TOCTOU）。
    """
    host = urllib.parse.urlparse(url).hostname
    if not host:
        return "missing host", []
    try:
        infos = _resolve_host(host, timeout)
    except concurrent.futures.TimeoutError:
        return f"dns_timeout: resolving host {host} exceeded {timeout}s", []
    except socket.gaierror:
        return f"cannot resolve host: {host}", []
    networks = _allowed_probe_networks()
    if not networks:
        # BUG-033 fail-closed：env 已设置但无一条合法网段时宁可全拒，
        # 绝不因配置错误退化为放行
        return "no valid CIDRs in YUANZI_PROBE_ALLOWED_CIDR; refusing to probe", []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not any(ip in network for network in networks):
            return (
                f"address {ip} outside allowed CIDRs (YUANZI_PROBE_ALLOWED_CIDR)",
                [],
            )
    return None, infos


# BUG-033：串行化「CIDR 校验 + 探测请求」临界区。_pinned_dns 靠
# monkeypatch 进程级的 socket.getaddrinfo 实现，并发探测必须排队，
# 避免钉扎互相串扰。
_PROBE_DNS_LOCK = threading.Lock()


@contextlib.contextmanager
def _pinned_dns(host: str, infos: List[Any]):
    """请求期间把 socket.getaddrinfo 钉在已验证的解析结果上（BUG-033）。

    否则 urlopen 内部会再次解析：攻击者控制的 DNS 可在校验时返回回环
    地址、建连时返回内网地址（DNS 重绑定），绕过 CIDR 检查。钉扎只
    覆盖同一 host；其他 host（如代理）委托原函数。http/https 语义
    （含 TLS SNI 与证书校验）不受影响。
    """
    original = socket.getaddrinfo

    def _pinned(h, port, *args, **kwargs):
        if h != host:
            return original(h, port, *args, **kwargs)
        # 按请求方要求的 socktype 过滤（http.client 用 SOCK_STREAM）；
        # 过滤结果仍是已验证地址集合的子集
        socktype = kwargs.get("type", args[1] if len(args) > 1 else 0)
        if socktype:
            matched = [info for info in infos if info[1] == socktype]
            if matched:
                return matched
        return infos

    socket.getaddrinfo = _pinned
    try:
        yield
    finally:
        socket.getaddrinfo = original


def probe_atom(
    conn: sqlite3.Connection,
    atom_id: str,
    timeout: float = 2.0,
    actor: str = "probe",
    max_retries: int = 3,
) -> Dict[str, Any]:
    """带乐观锁重试的探测入口（加固2）：并发写入冲突时重读重试。"""
    last_error: Optional[Exception] = None
    for _ in range(max_retries):
        try:
            return _probe_once(conn, atom_id, timeout=timeout, actor=actor)
        except ConcurrentModificationError as exc:
            last_error = exc
    raise ConcurrentModificationError(
        f"probe of '{atom_id}' failed after {max_retries} retries: {last_error}"
    )


def _probe_once(
    conn: sqlite3.Connection,
    atom_id: str,
    timeout: float = 2.0,
    actor: str = "probe",
) -> Dict[str, Any]:
    """真实请求原子的 health_url（缺省用 endpoint），按结果更新状态。

    - 2xx            -> running
    - 其他 HTTP 码   -> unreachable（有进程监听但不健康）
    - 连接错误/超时  -> unreachable
    - 非 http/https  -> invalid_url（不发请求，不改生命周期）

    探测结果写入 runtime_json（last_probe_at / last_probe_status /
    last_probe_latency_ms / consecutive_failures）。
    审计节流（BUG-022）：只有生命周期变化或探测结果类别变化时才记审计。
    探测前先把状态置为 probing（两阶段写入，进程崩溃可识别，BUG-017）。
    """
    atom = get_atom(conn, atom_id)
    if not atom:
        # 原子不存在，没有可依附审计的对象，直接返回
        return {
            "success": False,
            "error": "not_found",
            "message": f"Atom '{atom_id}' not found",
        }

    expected_counter = int(atom.get("version_counter") or 0)
    runtime = atom.get("runtime") or {}
    lifecycle = atom.get("lifecycle", {})
    old_status = lifecycle.get("status")

    def _persist(
        probe_status: str,
        ok: Optional[bool],
        latency_ms: Optional[float] = None,
        detail: str = "",
        expected_counter: int = 0,
    ) -> str:
        prev_probe_status = runtime.get("last_probe_status")
        runtime["last_probe_at"] = now_iso()
        runtime["last_probe_status"] = probe_status
        if latency_ms is not None:
            runtime["last_probe_latency_ms"] = latency_ms

        new_status = old_status
        if ok is not None:
            runtime["consecutive_failures"] = (
                0 if ok else int(runtime.get("consecutive_failures", 0)) + 1
            )
            if old_status in _PROBEABLE_STATUSES:
                target = "running" if ok else "unreachable"
                if target == old_status or _transition_allowed(old_status, target):
                    new_status = target
        # 始终写回计算结果：结果不变时把两阶段的 probing 标记还原（BUG-017）
        lifecycle["status"] = new_status
        lifecycle["updated_at"] = now_iso()

        cursor = conn.execute(
            f"UPDATE {REGISTRY_TABLE} SET runtime_json = ?, lifecycle_json = ?, "
            "updated_at = ?, version_counter = version_counter + 1 "
            "WHERE atom_id = ? AND version_counter = ?",
            (
                json.dumps(runtime, ensure_ascii=False),
                json.dumps(lifecycle, ensure_ascii=False),
                now_iso(),
                atom_id,
                expected_counter,
            ),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            raise ConcurrentModificationError(
                f"Atom '{atom_id}' was modified concurrently; retry probe"
            )
        conn.commit()

        if new_status != old_status or probe_status != prev_probe_status:
            parts = [probe_status]
            if latency_ms is not None:
                parts.append(f"{latency_ms}ms")
            if detail:
                parts.append(detail)
            _audit(
                conn, atom_id, "probe", old_status, new_status, actor, " ".join(parts)
            )
        return new_status

    url = runtime.get("health_url") or runtime.get("endpoint")
    if not url:
        # BUG-018：无端点也要留下探测痕迹与审计
        new_status = _persist("no_endpoint", ok=None, expected_counter=expected_counter)
        return {
            "success": False,
            "atom_id": atom_id,
            "error": "no_endpoint",
            "message": f"Atom '{atom_id}' has no health_url or endpoint",
            "old_status": old_status,
            "new_status": new_status,
        }

    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_PROBE_SCHEMES:
        new_status = _persist("invalid_url", ok=None, expected_counter=expected_counter)
        return {
            "success": False,
            "atom_id": atom_id,
            "error": "invalid_url",
            "message": f"Refusing to probe non-HTTP URL (scheme='{scheme or 'none'}')",
            "old_status": old_status,
            "new_status": new_status,
        }

    # M6.5b：目标地址 CIDR 限制（默认仅回环）。
    # BUG-033：校验与请求落在同一临界区，配合 DNS 钉扎防重绑定 TOCTOU。
    with _PROBE_DNS_LOCK:
        address_error, resolved_infos = _probe_address_error(url, timeout)
        if address_error:
            new_status = _persist(
                "blocked_address", ok=None, expected_counter=expected_counter
            )
            return {
                "success": False,
                "atom_id": atom_id,
                "error": "blocked_address",
                "message": f"Refusing to probe address: {address_error}",
                "old_status": old_status,
                "new_status": new_status,
            }

        # BUG-017 两阶段：先把可探测原子标记为 probing（静默，不记审计）
        if old_status in _PROBEABLE_STATUSES and old_status != "probing":
            lifecycle["status"] = "probing"
            lifecycle["updated_at"] = now_iso()
            conn.execute(
                f"UPDATE {REGISTRY_TABLE} SET lifecycle_json = ? WHERE atom_id = ?",
                (json.dumps(lifecycle, ensure_ascii=False), atom_id),
            )
            conn.commit()

        started = time.monotonic()
        detail = ""
        try:
            # 已验证的解析结果在请求期间钉住，防止二次解析被 DNS 翻转
            host = urllib.parse.urlparse(url).hostname or ""
            with _pinned_dns(host, resolved_infos):
                with urllib.request.urlopen(url, timeout=timeout) as resp:
                    code = resp.status
            ok = 200 <= code < 300
            probe_status = "ok" if ok else f"http_{code}"
        except urllib.error.HTTPError as exc:
            ok = False
            probe_status = f"http_{exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            ok = False
            probe_status = "connection_error"
            reason = getattr(exc, "reason", exc)
            detail = str(reason)
        latency_ms = round((time.monotonic() - started) * 1000, 1)

    new_status = _persist(
        probe_status, ok, latency_ms, detail, expected_counter=expected_counter
    )
    return {
        "success": True,
        "atom_id": atom_id,
        "ok": ok,
        "probe_status": probe_status,
        "latency_ms": latency_ms,
        "old_status": old_status,
        "new_status": new_status,
    }


def probe_atoms(
    conn: sqlite3.Connection,
    atom_ids: Optional[List[str]] = None,
    timeout: float = 2.0,
    actor: str = "probe",
) -> List[Dict[str, Any]]:
    """批量探测。atom_ids 为 None 时探测注册表里的所有原子。

    单个原子探测异常不会中断整个批次（BUG-014）。"""
    if atom_ids is None:
        atom_ids = [a["atom_id"] for a in list_atoms(conn)]
    results: List[Dict[str, Any]] = []
    for aid in atom_ids:
        try:
            results.append(probe_atom(conn, aid, timeout=timeout, actor=actor))
        except Exception as exc:  # noqa: BLE001 - 批量探测必须隔离单点失败
            results.append(
                {
                    "success": False,
                    "atom_id": aid,
                    "error": "probe_exception",
                    "message": str(exc),
                }
            )
    return results
