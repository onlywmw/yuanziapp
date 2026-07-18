"""QA execution: TC-SEC-001 .. TC-SEC-010 (OWASP Top 10).

PASS = threat mitigated. FAIL = vulnerability confirmed -> bug.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ATOMS = REPO / "atoms"
sys.path.insert(0, str(REPO / "mcp-yuanzi-bridge"))
import registry  # noqa: E402

results = []


def rec(tc, ok, note=""):
    results.append((tc, "PASS" if ok else "FAIL", note.replace("\n", " ")[:300]))


def load_core(atom_name):
    spec = importlib.util.spec_from_file_location(
        f"core_{atom_name}", ATOMS / atom_name / "core.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# TC-SEC-001 path traversal / arbitrary file read (A01)
fr = load_core("atom-file-read")
hosts = r"C:/Windows/System32/drivers/etc/hosts"
r1 = fr.handler({"path": hosts})
leaked = r1.get("status") == "success" and "localhost" in r1.get("data", {}).get("content", "")
rec("TC-SEC-001", not leaked,
    f"read system file -> status={r1.get('status')}; arbitrary-file-read {'CONFIRMED' if leaked else 'blocked'}")

# TC-SEC-002 SSRF (A10)
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b"INTERNAL-SECRET"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
hg = load_core("atom-http-get")
r_http = hg.handler({"url": f"http://127.0.0.1:{port}/internal"})
ssrf_http = r_http.get("status") == "success" and "INTERNAL-SECRET" in r_http["data"]["text"]
r_file = hg.handler({"url": "file:///C:/Windows/win.ini"})
ssrf_file = r_file.get("status") == "success"
srv.shutdown()
rec("TC-SEC-002", not (ssrf_http or ssrf_file),
    f"loopback internal fetched={ssrf_http}; file:// fetched={ssrf_file} -> SSRF {'CONFIRMED' if ssrf_http else 'partial'}")

# TC-SEC-003 bind 0.0.0.0 + no auth (A05/A07)
binds = {}
auth = {}
for server in sorted(ATOMS.glob("*/server.py")):
    src = server.read_text(encoding="utf-8")
    m = re.search(r'app\.run\(host="([^"]+)"', src)
    binds[server.parent.name] = m.group(1) if m else "?"
    auth[server.parent.name] = bool(re.search(r"token|api_key|Authorization|auth", src, re.I))
tpl = (REPO / "yuanzi-atom-templates" / "{{cookiecutter.atom_id}}" / "server.py").read_text(encoding="utf-8")
tpl_default = 'os.environ.get("HOST", RUNTIME.get("host", "0.0.0.0"))' in tpl
tpl_auth = bool(re.search(r"token|api_key|Authorization", tpl, re.I))
all_wild = all(h == "0.0.0.0" for h in binds.values())
rec("TC-SEC-003", not (all_wild and not any(auth.values())),
    f"atoms bind={set(binds.values())} auth={any(auth.values())}; template default host 0.0.0.0={tpl_default} auth={tpl_auth}")

# TC-SEC-004 no body size limit (A04)
has_limit = re.search(r"MAX|limit|length >|Content-Length.*<", tpl, re.I)
rec("TC-SEC-004", bool(has_limit),
    "template server._read_body reads Content-Length with no upper bound -> memory DoS possible")

# TC-SEC-005 SQL injection (A03) - extended check on category param
db = Path(tempfile.mkdtemp(prefix="qa-sec-")) / "s.db"
conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row
registry.ensure_registry_schema(conn)
registry.submit_atom(conn, {"atom_id": "com.sec.x", "name": "N", "description": "d",
                            "purpose": {"functions": [{"name": "f"}]},
                            "architecture": {"type": "skill", "runtime": "python",
                                             "interface": "i", "dependencies": []},
                            "ownership": {}})
r1 = registry.list_atoms(conn, search="' OR '1'='1")
r2 = registry.list_atoms(conn, category="x' AND 1=1--")
err = None
try:
    registry.list_atoms(conn, search="%'; DROP TABLE atom_registry;--")
    still = registry.compute_registry_stats(conn)["total_atoms"]
except Exception as e:
    err = str(e)
    still = -1
rec("TC-SEC-005", len(r1) == 0 and len(r2) == 0 and still == 1 and err is None,
    f"search_inj={len(r1)} category_inj={len(r2)} table_intact={still == 1}")

# TC-SEC-006 yaml.safe_load usage (A08)
uses = []
for p in [REPO / "yuanzi-cli" / "yuanzi_cli" / "meta.py",
          REPO / "yuanzi-atom-templates" / "{{cookiecutter.atom_id}}" / "server.py",
          REPO / "scripts" / "sync-to-device.py"]:
    src = p.read_text(encoding="utf-8")
    safe = "yaml.safe_load" in src
    unsafe = re.search(r"yaml\.load\(", src)
    uses.append((p.name, safe, bool(unsafe)))
rec("TC-SEC-006", all(s and not u for _, s, u in uses), str(uses))

# TC-SEC-007 hardcoded secrets / personal paths (A02/A05)
pat = re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{6,}")
hits = []
for p in REPO.rglob("*"):
    if p.is_dir() or ".git" in p.parts or p.suffix in {".png", ".pyc"}:
        continue
    try:
        t = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for m in pat.finditer(t):
        hits.append(f"{p.relative_to(REPO)}: {m.group(0)[:40]}")
cfg = (REPO / "yuanzi-config.yaml").read_text(encoding="utf-8")
personal_path = "C:/aaaaa" in cfg
rec("TC-SEC-007", len(hits) == 0 and not personal_path,
    f"secret-like hits={hits[:3]}; personal adb path in repo config={personal_path}")

# TC-SEC-008 error detail leakage (A05)
tpl_leak = '"error": str(exc)' in tpl or '{"ok": False, "error": str(exc)}' in tpl
atom_leak = '"message": str(e)' in (ATOMS / "atom-math-sum" / "core.py").read_text(encoding="utf-8")
rec("TC-SEC-008", not (tpl_leak or atom_leak),
    f"template returns str(exc) to client={tpl_leak}; atoms core returns str(e)={atom_leak}")

# TC-SEC-009 dependency pinning (A06)
pp = (REPO / "yuanzi-cli" / "pyproject.toml").read_text(encoding="utf-8")
unpinned = re.findall(r'"([a-z0-9-]+>=[^"]+)"', pp)
lock_exists = any((REPO / n).exists() for n in
                  ["requirements.lock", "poetry.lock", "uv.lock", "requirements.txt"])
rec("TC-SEC-009", lock_exists,
    f"deps use >= ranges: {unpinned}; lock file present={lock_exists}")

# TC-SEC-010 logging / audit (A09)
audit_ok = all(k in (REPO / "mcp-yuanzi-bridge" / "registry.py").read_text(encoding="utf-8")
               for k in ["actor", "created_at", "AUDIT_TABLE"])
atoms_have_accesslog = any("log_message" in s.read_text(encoding="utf-8")
                           for s in ATOMS.glob("*/server.py"))
rec("TC-SEC-010", audit_ok,
    f"registry audit fields present={audit_ok}; atoms access logging={atoms_have_accesslog} (none -> suggest)")

print("=" * 70)
for tc, status, note in results:
    print(f"{tc} | {status} | {note}")
fails = [t for t, s, _ in results if s == "FAIL"]
print("=" * 70)
print(f"TOTAL {len(results)}  PASS {len(results)-len(fails)}  FAIL {len(fails)}")
if fails:
    print("VULNS:", ",".join(fails))
