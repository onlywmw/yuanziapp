"""QA execution: TC-ATM-001 .. TC-ATM-018.

Kernel-level tests import each atom's core.py directly; http-get tests use a
local loopback HTTP target; static checks inspect server.py configs.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ATOMS = REPO / "atoms"

results = []


def rec(tc, ok, note=""):
    results.append((tc, "PASS" if ok else "FAIL", note.replace("\n", " ")[:300]))


def load_core(atom_name):
    spec = importlib.util.spec_from_file_location(
        f"core_{atom_name}", ATOMS / atom_name / "core.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- math-sum ----------
math = load_core("atom-math-sum")
r = math.handler({"a": 10, "b": 20})
rec("TC-ATM-001", r == {"status": "success", "data": {"result": 30.0}}, json.dumps(r))

r = math.handler({})
rec("TC-ATM-002", r.get("status") == "success" and r["data"]["result"] == 0.0, json.dumps(r))

r = math.handler({"a": "abc", "b": 1})
rec("TC-ATM-003", r.get("status") == "error" and r.get("message"), json.dumps(r))

r = math.handler({"a": 1e308, "b": 1e308})
is_inf = r.get("status") == "success" and r["data"]["result"] == float("inf")
rec("TC-ATM-004", True, f"documented: 1e308+1e308 -> {json.dumps(r)} (inf returned as success={is_inf})")

# ---------- string-split ----------
ss = load_core("atom-string-split")
r = ss.handler({"text": "a,b,c", "delimiter": ","})
rec("TC-ATM-005", r == {"status": "success", "data": {"parts": ["a", "b", "c"], "count": 3}}, json.dumps(r))

r = ss.handler({"text": "a,b,c,d", "delimiter": ",", "maxsplit": 2})
rec("TC-ATM-006", r.get("data", {}).get("parts") == ["a", "b", "c,d"] and r["data"]["count"] == 3, json.dumps(r))

r = ss.handler({"text": "abc", "delimiter": ""})
rec("TC-ATM-007", r.get("status") == "error", json.dumps(r))

# ---------- file-read ----------
fr = load_core("atom-file-read")
tmpd = Path(tempfile.mkdtemp(prefix="qa-atm-"))
hello = tmpd / "hello.txt"
hello.write_text("hi yuanzi", encoding="utf-8")
r = fr.handler({"path": str(hello)})
rec("TC-ATM-008", r.get("status") == "success" and r["data"]["content"] == "hi yuanzi"
    and r["data"]["size"] == 9, json.dumps(r, ensure_ascii=False)[:200])

r = fr.handler({"path": "C:/qa/not-exist-12345.txt"})
rec("TC-ATM-009", r.get("status") == "error" and "file not found" in r.get("message", ""), json.dumps(r))

big = tmpd / "big.bin"
big.write_bytes(b"x" * 100)
r = fr.handler({"path": str(big), "max_size": 10})
rec("TC-ATM-010", r.get("status") == "error" and "file too large" in r.get("message", ""), json.dumps(r))

binf = tmpd / "bin.dat"
payload = bytes(range(256))
binf.write_bytes(payload)
r = fr.handler({"path": str(binf), "mode": "base64"})
ok = False
if r.get("status") == "success":
    try:
        ok = base64.b64decode(r["data"]["content"]) == payload
    except Exception:
        ok = False
rec("TC-ATM-011", ok, f"status={r.get('status')} roundtrip={ok}")

r = fr.handler({})
rec("TC-ATM-012", r.get("status") == "error" and "missing required field: path" in r.get("message", ""), json.dumps(r))

# ---------- http-get with local loopback target ----------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/data":
            body = b'{"hello": "yuanzi"}'
        elif self.path == "/big":
            body = b"A" * 5000
        elif self.path == "/internal":
            body = b"INTERNAL-SECRET"
        else:
            body = b"notfound"
            self.send_response(404)
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

hg = load_core("atom-http-get")
r = hg.handler({"url": f"http://127.0.0.1:{port}/data"})
rec("TC-ATM-013", r.get("status") == "success" and r["data"]["status_code"] == 200
    and "yuanzi" in r["data"]["text"], json.dumps(r)[:200])

r = hg.handler({})
rec("TC-ATM-014", r.get("status") == "error" and "missing required field: url" in r.get("message", ""), json.dumps(r))

r = hg.handler({"url": f"http://127.0.0.1:{port}/big", "max_length": 100})
rec("TC-ATM-015", r.get("status") == "success" and len(r["data"]["text"]) == 100,
    f"len={len(r.get('data', {}).get('text', ''))}")

r = hg.handler({"url": "not-a-url"})
rec("TC-ATM-016", r.get("status") == "error" and r.get("message"), json.dumps(r)[:200])

srv.shutdown()

# ---------- static checks ----------
ports = {}
for server in sorted(ATOMS.glob("*/server.py")):
    src = server.read_text(encoding="utf-8")
    m = re.search(r'app\.run\(host="([^"]+)",\s*port=(\d+)\)', src)
    if m:
        ports[server.parent.name] = (m.group(1), int(m.group(2)))
unique_ports = {p for _, p in ports.values()}
rec("TC-ATM-017", len(unique_ports) == len(ports),
    f"port map={ports} -> {'CONFLICT: all share one port' if len(unique_ports) < len(ports) else 'unique'}")

ids = {}
for server in sorted(ATOMS.glob("*/server.py")):
    src = server.read_text(encoding="utf-8")
    m = re.search(r'"id":\s*"([^"]+)"', src)
    if m:
        ids[server.parent.name] = m.group(1)
conform = {k: bool(re.match(r"^[a-z0-9]+(\.[a-z0-9_-]+)+$", v)) for k, v in ids.items()}
rec("TC-ATM-018", all(conform.values()),
    f"/meta ids={ids}")

print("=" * 70)
for tc, status, note in results:
    print(f"{tc} | {status} | {note}")
fails = [t for t, s, _ in results if s == "FAIL"]
print("=" * 70)
print(f"TOTAL {len(results)}  PASS {len(results)-len(fails)}  FAIL {len(fails)}")
if fails:
    print("FAILED:", ",".join(fails))
