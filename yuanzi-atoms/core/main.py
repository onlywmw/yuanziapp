#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yuanzi Core - 原子化注册中心与事件总线
端口：8080
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
import db

CORE_PORT = int(os.environ.get("YUANZI_CORE_PORT", "8080"))
CORE_HOST = os.environ.get("YUANZI_CORE_HOST", "127.0.0.1")


def now_utc() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def ok_response(data: Any) -> Dict[str, Any]:
    return {"ok": True, "data": data}


def err_response(error: str) -> Dict[str, Any]:
    return {"ok": False, "error": error}


def send_json(
    handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.wfile.write(body)


def read_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw) if raw else {}


def route_health() -> Tuple[int, Dict[str, Any]]:
    return 200, ok_response({"status": "ok", "version": "v1", "atom": "yuanzi-core"})


def route_graph() -> Tuple[int, Dict[str, Any]]:
    atoms = db.list_atoms()
    caps = db.list_capabilities()

    nodes = [
        {
            "id": "yuanzi-core",
            "label": "Yuanzi Core",
            "type": "core",
            "status": "online",
        },
        {"id": "widgetmcp", "label": "组件 MCP", "type": "client", "status": "online"},
    ]
    edges = [
        {"source": "widgetmcp", "target": "yuanzi-core"},
    ]

    for atom in atoms:
        atom_id = atom["atom_id"]
        nodes.append(
            {
                "id": atom_id,
                "label": atom["label"],
                "type": atom["atom_type"],
                "status": atom["status"],
                "endpoint": atom["endpoint"],
                "capabilities": atom["capabilities"],
            }
        )
        edges.append({"source": "yuanzi-core", "target": atom_id})

    # 根据 capability 增加细粒度连线
    for cap in caps:
        target = cap["target"]
        if target == "yuanzi-core":
            continue
        # 找 target 对应的 atom_id
        atom_id = None
        for atom in atoms:
            if atom["atom_id"] == target or atom["label"] == target:
                atom_id = atom["atom_id"]
                break
        if atom_id and atom_id != "yuanzi-core":
            edges.append(
                {"source": "yuanzi-core", "target": atom_id, "label": cap["tool_id"]}
            )

    return 200, ok_response({"nodes": nodes, "edges": edges})


def route_register(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    atom_id = body.get("atom_id")
    label = body.get("label", atom_id)
    atom_type = body.get("type", "atom")
    endpoint = body.get("endpoint", "")
    capabilities = body.get("capabilities", [])
    if not atom_id or not endpoint:
        return 400, err_response("Missing atom_id or endpoint")
    db.register_atom(atom_id, label, atom_type, endpoint, capabilities)
    return 200, ok_response({"atom_id": atom_id, "status": "registered"})


def route_command(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    tool_id = body.get("tool_id")
    if not tool_id:
        return 400, err_response("Missing tool_id")
    db.insert_event("external", tool_id, body.get("args", {}), {}, "pending")
    return 202, ok_response({"tool_id": tool_id, "status": "queued"})


def route_poll_browser_command() -> Tuple[int, Dict[str, Any]]:
    cmd = db.poll_pending_browser_command()
    if cmd is None:
        return 200, ok_response(None)
    return 200, ok_response(
        {
            "event_id": cmd["id"],
            "tool_id": cmd["tool_id"],
            "args": cmd["args"],
        }
    )


def route_event(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    source = body.get("source", "app")
    tool_id = body.get("tool_id")
    args = body.get("args", {})
    result = body.get("result", {})
    status = body.get("status", "success")
    db.insert_event(source, tool_id, args, result, status)
    return 200, ok_response({"status": "recorded"})


class CoreHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        print(f"[Yuanzi-CORE] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        path = self.path
        if path == "/health":
            status, payload = route_health()
        elif path == "/graph":
            status, payload = route_graph()
        else:
            status, payload = 404, err_response("Not Found")
        send_json(self, status, payload)

    def do_POST(self) -> None:
        path = self.path
        try:
            body = read_body(self)
        except Exception as e:
            send_json(self, 400, err_response(f"Invalid JSON: {e}"))
            return

        if path == "/register":
            status, payload = route_register(body)
        elif path == "/agent/command":
            status, payload = route_command(body)
        elif path == "/agent/command/poll":
            status, payload = route_poll_browser_command()
        elif path == "/agent/event":
            status, payload = route_event(body)
        else:
            status, payload = 404, err_response("Not Found")
        send_json(self, status, payload)


def main() -> None:
    db.init_db()
    db.seed_capabilities()
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((CORE_HOST, CORE_PORT), CoreHandler)
    print(f"[Yuanzi-CORE] listening on {CORE_HOST}:{CORE_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
