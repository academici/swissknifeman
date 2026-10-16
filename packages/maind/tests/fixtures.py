"""Synthetic fittings for unittest: isolated Env, configs, fake memory daemon.

Tests do not touch the real node/daemon: everything runs in temporary directories, and
HTTP-contract agentmemory emulates FakeMemoryServer on a free port."""
import contextlib
import io
import json
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# In case of direct launch: we guarantee lib/ on the way (test.sh and so puts PYTHONPATH).
_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from maind.common import Env

MINIMAL_III_CONFIG = "workers:\n  - name: iii-http\n    config:\n      port: 4111\n"


def make_repo(tmp):
    """Creates a synthetic node root maind in tmp + isolated HOME.
    Returns (root: Path, env: Env)."""
    tmp = Path(tmp)
    root = tmp / "maind"
    home = tmp / "home"
    (root / "config" / "memory").mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    (root / "config" / "memory" / "iii-config.yaml").write_text(
        MINIMAL_III_CONFIG, encoding="utf-8")
    return root, Env(root, home=home)


def write_maind_config(root, **overrides):
    """Writes valid config.json to the root of the node; overrides are merged on top of the default.
    (standalone-test layout: no packages/ nearby → resolver is waiting config.json in root)."""
    config = {
        "_version": "1",
        "node": {"id": "test", "name": "Test", "role": "primary"},
        "memory": {"http_port": 4111, "stream_port": 4112},
        "graph": {"adapter": "federation"},
        "projects": [
            {"id": "alpha", "name": "Alpha", "type": "node-package",
             "status": "active", "dependencies": ["maind"], "skills": ["x"]},
        ],
    }
    config.update(overrides)
    path = Path(root) / "config.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def write_brain_projects(root, projects=None):
    """Writes brain-REAL .projects.json (diagram {name,enabled,vault_path,repo,folders})."""
    if projects is None:
        projects = [
            {"name": "Brain", "enabled": True, "vault_path": "/v/Brain",
             "repo": "/r/brain", "folders": ["docs", "docs-public"]},
            {"name": "Swiss Knife Man", "enabled": True, "vault_path": "/v/SKM",
             "repo": "/r/skm", "folders": ["docs"]},
        ]
    data = {"version": 1, "debounce_seconds": 300, "sync_folders": "all",
            "watch_vault": True, "watch_repo": True, "projects": projects}
    path = Path(root) / ".projects.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def capture(fn, *args, **kwargs):
    """Performs fn with interception stdout. Returns (result, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args, **kwargs)
    return result, buf.getvalue()


# ── fake memory daemon (agentmemory HTTP-contract) ───────────────────────
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence in tests
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        """True, if the protected endpoint passes the request: server WITHOUT secret -
        always (like a living demon without AGENTMEMORY_SECRET); with secret - only
        correct `Authorization: Bearer <secret>` (like middleware::api-auth)."""
        secret = getattr(self.server, "secret", None)
        if not secret:
            return True
        return self.headers.get("Authorization") == f"Bearer {secret}"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/agentmemory/health":
            self._send(200, {"status": "ok"})   # ALWAYS public - even with a secret
        elif parsed.path == "/agentmemory/memories":
            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return
            q = parse_qs(parsed.query)
            ns = (q.get("namespace") or [""])[0]
            mems = self.server.memories.get(ns, []) if ns else \
                [m for bucket in self.server.memories.values() for m in bucket]
            self._send(200, {"memories": mems, "total": len(mems)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not self._authorized():
            self._send(401, {"error": "unauthorized"})
            return
        ns = payload.get("namespace", "")
        if parsed.path == "/agentmemory/remember":
            self.server._seq += 1
            mid = f"mem_fake_{self.server._seq}"
            self.server.memories.setdefault(ns, []).append(
                {"id": mid, "content": payload.get("content", ""), "type": payload.get("type"),
                 "createdAt": datetime.now(timezone.utc).isoformat()})
            self._send(201, {"success": True,
                             "memory": {"id": mid, "content": payload.get("content", "")}})
        elif parsed.path == "/agentmemory/search":
            query = (payload.get("query") or "").lower()
            limit = payload.get("limit")
            results = [{"observation": {"id": m["id"], "narrative": m["content"],
                                        "createdAt": m.get("createdAt"),
                                        "title": m["content"], "facts": [m["content"]]},
                        "score": 1.0}
                       for m in self.server.memories.get(ns, [])
                       if query in m["content"].lower()]
            if isinstance(limit, int) and limit >= 0:
                results = results[:limit]
            self._send(200, {"results": results})
        elif parsed.path == "/agentmemory/forget":
            # agentmemory is waiting memoryId; without it - 400 (like a living demon).
            mid = payload.get("memoryId")
            if not mid:
                self._send(400, {"error": "memoryId required"})
                return
            deleted = 0
            for arr in self.server.memories.values():
                before = len(arr)
                arr[:] = [m for m in arr if m.get("id") != mid]
                deleted += before - len(arr)
            self._send(200, {"success": True, "deleted": deleted})
        else:
            self._send(404, {"error": "not found"})


class FakeMemoryServer:
    """Context manager: HTTP-server with agentmemory-contract on a free port.
    `with FakeMemoryServer() as url:` → basic URL. Memory - in self.memories.
    `secret` — optional: protected endpoints (all except /agentmemory/health —
    it is ALWAYS public, like a live engine) 401'yat without the correct bearer'a."""

    def __init__(self, secret=None):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.memories = {}
        self.httpd._seq = 0
        self.httpd.secret = secret
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self):
        host, port = self.httpd.server_address
        return f"http://127.0.0.1:{port}"

    def __enter__(self):
        self.thread.start()
        return self.url

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


FAKE_ANALYST = '''#!{python}
import json, sys
with open({log!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
spec = json.load(open({spec!r}, encoding="utf-8"))
if spec.get("exit"):
    sys.stderr.write(spec.get("stderr", "boom") + "\\n")
    sys.exit(spec["exit"])
sys.stdout.write(spec["stdout"] if "stdout" in spec else json.dumps(spec[sys.argv[2]]))
'''


def make_fake_analyst(tmp, *, show=None, codegraph=None, exit_code=0, stdout=None):
    """A stand-in for ``analyst``: an executable script in ``tmp`` that prints a fixture for ``runs show`` or
    ``runs codegraph``. Return ``(path, calls)``; ``calls()`` lists the argv each call received.
    """
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    spec = tmp / "fake-analyst.json"
    log = tmp / "fake-analyst.log"
    body = {"show": show, "codegraph": codegraph}
    if exit_code:
        body["exit"] = exit_code
    if stdout is not None:
        body["stdout"] = stdout
    spec.write_text(json.dumps(body), encoding="utf-8")
    script = tmp / "fake-analyst"
    script.write_text(FAKE_ANALYST.format(python=sys.executable, log=str(log), spec=str(spec)), encoding="utf-8")
    script.chmod(0o755)

    def calls():
        if not log.is_file():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    return str(script), calls


def lookup_payload(project, *, report=None, status=None, reason=None, codegraph=None, events=()):
    """A ``run-lookup/v1`` document as ``analyst runs show --json`` prints it."""
    status = status or ("found" if report is not None else "missing")
    return {"$schema": "urn:swissknifeman:analyst:run-lookup:v1", "project": str(project),
            "lookup": {"status": status, "path": None, "reason": reason}, "report": report,
            "codegraph": codegraph, "events": list(events)}
