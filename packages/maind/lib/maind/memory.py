"""Node Memory: Lifecycle agent-memory demon + HTTP-wrapper with scope'ami.

agent-memory — external Node-demon (@agentmemory/agentmemory on iii-sdk); maind him
ORCHESTRATED (start/stop/status), and does not rewrite. Ports are taken from env/config
(no hardcodes), so as not to conflict with another node (for example Brain).

HTTP-daemon contract: GET /health · POST /memories {namespace,type,text} ·
GET /search?namespace=&q= → {results:[{score,text}]}."""
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

from core.http import HTTPUnauthorizedError

from .common import (die, http_get_json, http_post_json, parse_args, pid_alive,
                     ping, warn)
from .config import load_config
from .constants import (DIGEST_BUDGET_CHARS, DIGEST_ITEM_MAX_CHARS, DIGEST_MIN_TAIL_CHARS,
                        DIGEST_SHARED_MAX, DIGEST_TRUNCATE_SUFFIX, MEMORY_HEAVY_TIMEOUT_S,
                        MEMORY_HTTP_PORT, MEMORY_LIGHT_TIMEOUT_S, MEMORY_RETRIES,
                        MEMORY_RETRY_BACKOFF_S, MEMORY_STREAM_PORT, MEMORY_WORKERS)


# ── port resolution/URL (env → config → default) ───────────────────────────
def resolve_ports(env, config):
    """(http_port, stream_port, url). Priority: env (AGENTMEMORY_*) → config.memory
    → defaults 4111/4112. URL — from AGENTMEMORY_URL or http://127.0.0.1:<http_port>."""
    mem = (config or {}).get("memory") or {}
    http_port = int(os.environ.get("AGENTMEMORY_PORT")
                    or mem.get("http_port") or MEMORY_HTTP_PORT)
    stream_port = int(os.environ.get("AGENTMEMORY_STREAM_PORT")
                      or mem.get("stream_port") or MEMORY_STREAM_PORT)
    url = (os.environ.get("AGENTMEMORY_URL") or mem.get("url")
           or f"http://127.0.0.1:{http_port}")
    return http_port, stream_port, url.rstrip("/")


def health(url):
    """True, if the daemon responds to /agentmemory/health (or /livez). Both endpoints
    are ALWAYS public in the engine (even with the specified AGENTMEMORY_SECRET) — this is NOT a check
    authorization, only «demon alive» (see check_auth for 401 vs not available)."""
    return (ping(f"{url}/agentmemory/health", timeout=3)
            or ping(f"{url}/agentmemory/livez", timeout=3))


# ── node role (ADR-0001 p.1/clause 5, D27/D80) ────────────────────────────────────
def memory_role(config):
    return ((config or {}).get("memory") or {}).get("role", "standalone")


def refuse_if_client_role(config):
    """die(), if this node is client: local memory daemon NOT raised -
    the second writer breaks the uniqueness of option 1 (ADR-0001 p.1/clause 5, D27).
    The ban is a CODE, not documentation (Implementation Rules P4.2)."""
    if memory_role(config) == "client":
        die("node role memory.role='client' — local memory daemon NOT raised "
            "(the second writer breaks cross-machine memory, ADR-0001). Use "
            "memory host by memory.url or change memory.role on this machine.")


# ── bind-daemon address: machine address does NOT live in tracked-config ───────────────────
_BIND_FORBIDDEN = {"0.0.0.0", "::", "0:0:0:0:0:0:0:0"}


def lan_address():
    """Main LAN-IPv4 THIS car (UDP-connect without sending packets) or None."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return None if address.startswith("127.") else address


def resolve_bind_host(config):
    """Address bind for iii-http, specified by NODE, not by repository: env `AGENTMEMORY_BIND_HOST`
    → `memory.bind_host` in config.json (gitignored). `auto` — LAN-address of the current machine.
    None → tracked-the template remains as is (loopback). Non-loopback is only valid for
    memory.role='host'; `0.0.0.0`/`::` are prohibited (ADR-0001, D28)."""
    mem = (config or {}).get("memory") or {}
    value = (os.environ.get("AGENTMEMORY_BIND_HOST") or mem.get("bind_host") or "").strip()
    if not value:
        return None
    if value == "auto":
        value = lan_address()
        if value is None:
            die("memory.bind_host='auto': LAN-the address of this machine is not defined - specify "
                "AGENTMEMORY_BIND_HOST/memory.bind_host explicitly or connect the network")
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        die(f"memory.bind_host='{value}' — pending IP-address or 'auto'")
    if value in _BIND_FORBIDDEN or parsed.is_unspecified:
        die("memory.bind_host: bind to all interfaces (0.0.0.0/::) is prohibited - please specify specific "
            "LAN-address or 'auto' (ADR-0001, D28)")
    if not parsed.is_loopback and memory_role(config) != "host":
        die(f"memory.bind_host='{value}' not loopback, but memory.role != 'host' — LAN-bind "
            "is only enabled on host-memory machine (ADR-0001)")
    return value


def effective_memory_config(env, config):
    """Path iii-config for the daemon. Tracked-template ported (host: 127.0.0.1); address of this
    of the machine is substituted into the RUNTIME copy `data/iii-config.runtime.yaml` (gitignored) —
    transfer to another computer = change `memory.bind_host`/`auto`, rather than editing the repository."""
    host = resolve_bind_host(config)
    if host is None:
        return env.memory_config
    lines = env.memory_config.read_text(encoding="utf-8").splitlines()
    out, in_http, done = [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- name:"):
            in_http = stripped == "- name: iii-http"
        if in_http and not done and stripped.startswith("host:"):
            line = f"{line[:len(line) - len(line.lstrip())]}host: {host}"
            done = True
        out.append(line)
    if not done:
        die(f"in {env.memory_config} not found workers[iii-http].host — bind-address cannot be substituted")
    env.data_dir.mkdir(parents=True, exist_ok=True)
    target = env.data_dir / "iii-config.runtime.yaml"
    target.write_text("# generated maind from tracked-template; do not edit or commit\n"
                      + "\n".join(out) + "\n", encoding="utf-8")
    return target


# ── authentication (ADR-0001 p.3/clause 4, D29) ───────────────────────────────────
def resolve_secret(env, config):
    """Bearer-token for protected memory calls. Order (ADR-0001): env
    `AGENTMEMORY_SECRET` → `memory.secret_file` (path to 0600 file; relative -
    from node root) → no secret (anonymous local daemon, like today - default
    doesn't change anything)."""
    env_secret = os.environ.get("AGENTMEMORY_SECRET")
    if env_secret:
        return env_secret
    secret_file = ((config or {}).get("memory") or {}).get("secret_file")
    if not secret_file:
        return None
    path = Path(os.path.expanduser(secret_file))
    if not path.is_absolute():
        path = env.root / path
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError as e:
        warn(f"memory.secret_file not readable ({path}: {e}) — memory calls will proceed without a token")
        return None


def auth_headers(secret):
    """{'Authorization': 'Bearer <secret>'} or None (without a secret - like today,
    headers don't work at all)."""
    return {"Authorization": f"Bearer {secret}"} if secret else None


def check_auth(url, headers, *, timeout=MEMORY_LIGHT_TIMEOUT_S):
    """Distinguishes «not available» from «unauthorized» on protected endpoint (findings
    §2: /agentmemory/health is ALWAYS public and does not give 401 - the truth about bearer you can
    find out only with a real protected call). None — secret not configured (check
    not applicable) · True — authorized · False — the demon responded with 401."""
    if not headers:
        return None
    try:
        http_post_json(f"{url}/agentmemory/search",
                       {"query": "__maind_auth_probe__", "namespace": "__maind_auth_probe__",
                        "limit": 1}, headers=headers, timeout=timeout)
        return True
    except HTTPUnauthorizedError:
        return False
    except RuntimeError:
        return None   # not available/another error - not about authorization


def unavailable_message(config, url):
    """Role-aware memory inaccessibility text (single cut-in point MCP,
    `_run_tool` in mcp.py): on client We do NOT prompt you to raise the local daemon - this is
    instructions to create a second writer (findings §2 «in)»)."""
    if memory_role(config) == "client":
        return f"memory host {url} not available (role client — local daemon does not rise)"
    return f"memory daemon not running ({url}) — maind start --only memory"


def _retry_read(fn, *, retries=MEMORY_RETRIES, backoff=MEMORY_RETRY_BACKOFF_S):
    """Retrays ONLY for read-paths (export/digest) — contract `store` does not carry
    operation-id, mutation retry risks double (ADR-0001 clause 5, `research/06` §5),
    therefore store/forget are NOT wrapped around them. HTTPUnauthorizedError does not retract -
    the same token will give the same 401 (findings §6 — retrays against transient-channel failure,
    doesn't mind authorization)."""
    last = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except HTTPUnauthorizedError:
            raise
        except RuntimeError as e:
            last = e
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    raise last


def _read_pid(env):
    if not env.memory_pidfile.exists():
        return None
    try:
        return int(env.memory_pidfile.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


# ── daemon life cycle ────────────────────────────────────────────────────
def _daemon_argv(env, config):
    """(cmd, child_env, url) to run Node-memory daemon. Common for start()/run() —
    both paths must refuse the role client (ADR-0001 clause 5, D27), so check
    here, and not in each of them separately. Checks node and the daemon binary -
    otherwise die with a hint."""
    refuse_if_client_role(config)
    http_port, stream_port, url = resolve_ports(env, config)
    if shutil.which("node") is None:
        die("node not found in PATH — agent-memory this Node-demon")
    bin_path = env.root / "node_modules" / ".bin" / "agentmemory"
    if not bin_path.exists():
        die("agentmemory not installed - run `npm install` at the root maind "
            "(memory daemon @agentmemory/agentmemory)")
    cmd = ["node"]
    if env.env_file.exists():
        cmd.append(f"--env-file={env.env_file}")
    cmd.append(str(bin_path))
    child_env = {
        **os.environ,
        "AGENTMEMORY_PORT": str(http_port),
        "AGENTMEMORY_STREAM_PORT": str(stream_port),
        "AGENTMEMORY_URL": url,
        "AGENTMEMORY_III_CONFIG": str(effective_memory_config(env, config)),
    }
    return cmd, child_env, url


def run_foreground(env, config):
    """Start memory daemon in FOREIGN (for systemd Type=simple): exec node,
    replacing the current process - systemd tracks the demon as MAINPID and himself rules the restart.
    If successful, it is NOT returned."""
    cmd, child_env, _ = _daemon_argv(env, config)
    env.data_dir.mkdir(parents=True, exist_ok=True)
    # exec saves PID → pidfile correctly points to node, and `maind memory
    # status`/`stop` see the real process (even under control systemd).
    env.memory_pidfile.write_text(str(os.getpid()), encoding="utf-8")
    os.chdir(str(env.root))
    os.execvpe(cmd[0], cmd, child_env)


def start(env, config, *, detach=True, timeout_s=10):
    """Launches Node-daemon in a separate session, writes pidfile, is waiting health. 0 — success."""
    _, stream_port, url = resolve_ports(env, config)
    if health(url):
        print(f"memory already running: {url}")
        return 0
    env.data_dir.mkdir(parents=True, exist_ok=True)
    cmd, child_env, _ = _daemon_argv(env, config)
    log = open(env.memory_log, "ab")
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(env.root), env=child_env,
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=detach)
    finally:
        log.close()
    env.memory_pidfile.write_text(str(proc.pid), encoding="utf-8")

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if health(url):
            print(f"memory started: {url} (pid {proc.pid}, stream :{stream_port}, "
                  f"service maind)")
            return 0
        if proc.poll() is not None:
            die(f"memory daemon exited immediately (code {proc.returncode}) — "
                f"see log {env.memory_log}")
        time.sleep(0.5)
    die(f"memory did not rise beyond {timeout_s}s on {url} — check the port/config, "
        f"see log {env.memory_log}")


def stop(env, config, *, timeout_s=5):
    """Stops a daemon started via maind (SIGTERM→SIGKILL). The Alien does not touch."""
    _, _, url = resolve_ports(env, config)
    pid = _read_pid(env)
    if pid is None:
        if health(url):
            warn(f"daemon responds to {url}, but not launched via maind (no pidfile) — "
                 f"do not stop someone else's process")
        else:
            print("memory not running")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        env.memory_pidfile.unlink(missing_ok=True)
        print("process is already dead - pidfile cleared")
        return 0
    deadline = time.time() + timeout_s
    while time.time() < deadline and health(url):
        time.sleep(0.3)
    if health(url):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass  # process has already disappeared between health-checking and SIGKILL — that was the goal
    env.memory_pidfile.unlink(missing_ok=True)
    print(f"memory stopped (pid {pid})")
    return 0


def status(env, config):
    """Memory snapshot for status/doctor/MCP."""
    http_port, stream_port, url = resolve_ports(env, config)
    pid = _read_pid(env)
    running = health(url)
    alive = pid_alive(pid) if pid is not None else None
    return {
        "running": running,
        "url": url,
        "http_port": http_port,
        "stream_port": stream_port,
        "pid": pid,
        "pid_alive": alive,
        "pidfile_stale": pid is not None and alive is False,
        "owned": pid is not None,
        "workers": [{"name": w, "state": "up" if running else "down"}
                    for w in MEMORY_WORKERS],
        "stream_up": ping(f"http://127.0.0.1:{stream_port}/", timeout=2)
        if running else False,
    }


# ── HTTP-wrapper with scope'ami + INSULATION ON SIDE maind ─────────────────────
# agentmemory 0.9.x: REST under the prefix /agentmemory/* (checked with living demon).
#
# IMPORTANT: the daemon is a SINGLE global pool. Empirically (alive curl) field `namespace`
# in remember/search/list IS IGNORED and `type` daemon OVERRIDES (classifier).
# Only saved verbatim `content`. Therefore, insulation according to scope provides CAM
# maind: when recording we embed scope-marker to the beginning of the content, when reading - filter
# results for the marker and remove it. This is the only reliable channel on this version
# engine (see docs/maind/guide/federation.md — «side insulation maind»).
SCOPE_MARK_RE = re.compile(r"^\[\[s:(?P<scope>[^\]]+)\]\]\s?")
# Candidates from the GLOBAL pool before filtering by scope. The pool is common to all ecosystem projects
# (17+), so the small window supplanted the relevant facts of the desired scope strangers (crowding).
# Take it wider; at saturation (the demon returned exactly the limit) we warn you - the facts may not fit.
RECALL_LIMIT = 200
# Cap for shared-scope'ov (ns:*/global) when project:<id>-expansion in _recall_union (mcp.py):
# without it one common ns: (e.g. ns:axioma, 47 records) hammered the answer and supplanted the private one
# scope project (e.g. 2 entries) — measured on 6 projects, 84-96% response from shared
# Private scope remains without a cap (RECALL_LIMIT) — recall purposeful, not passive SessionStart-injection (unlike
# digest, where shared_max=0 cuts shared to zero, see DIGEST_SHARED_MAX/select_digest_items).
RECALL_SHARED_LIMIT = 40


def mark_scope(scope, value):
    """Embed scope-marker to the beginning of the content: the only channel that is a daemon
    saves verbatim (namespace ignores, type overrides)."""
    return f"[[s:{scope}]] {value}"


def split_scope(text):
    """(scope|None, clean_text) from content. scope — OWNER (first token; puts it
    mark_scope when recording, cannot be faked). Remove ALL leading markers `[[s:…]]` — in case
    nested/repeated in the content to marker-artifacts were not leaked to the SERP. Unlabeled
    (legacy/alien) → (None, text)."""
    m = SCOPE_MARK_RE.match(text or "")
    if not m:
        return None, text
    owner, rest = m.group("scope"), text[m.end():]
    while True:                       # remove residual leading markers (we do not change the owner)
        m2 = SCOPE_MARK_RE.match(rest)
        if not m2:
            return owner, rest
        rest = rest[m2.end():]


def store(url, scope, key, value, headers=None):
    """Save fact: POST /agentmemory/remember. scope is embedded in the CONTENT with a marker
    `[[s:<scope>]]` (demon ignores namespace and overrides type — is the only one
    reliable isolation channel on the side maind). `namespace`/`type` we send it as it was - on
    future, if the engine starts to respect them. `headers` — bearer-authentication (ADR-0001),
    without a secret are not transmitted at all (default does not change anything)."""
    return http_post_json(f"{url}/agentmemory/remember",
                          {"namespace": scope, "content": mark_scope(scope, value),
                           "type": key}, headers=headers)


EPHEMERAL_KEYS = {"progress", "plan-progress", "checkpoint", "session-log"}
ACTIVE_HANDOFF_MARKER = "[active-handoff]"


def store_managed(url, scope, key, value, headers=None):
    """Apply the durable-memory write policy before storing a fact.

    Session/checkpoint journals belong in repository artifacts.  ``active-handoff``
    is the single mutable continuity slot and is replaced atomically enough for the
    underlying append-only engine (forget old slots, then write one current value).
    """
    normalized = (key or "fact").strip().lower()
    if normalized in EPHEMERAL_KEYS:
        raise ValueError("ephemeral progress is not durable memory; update the repository "
                         "handoff or use key=active-handoff")
    if normalized != "active-handoff":
        return store(url, scope, key, value, headers=headers)
    text = value if value.startswith(ACTIVE_HANDOFF_MARKER) else \
        f"{ACTIVE_HANDOFF_MARKER} {value}"
    for item in export(url, scope, headers):
        raw = item.get("content") or item.get("narrative") or item.get("title") or ""
        owner, clean = split_scope(raw)
        if owner == scope and (clean or "").startswith(ACTIVE_HANDOFF_MARKER):
            mid = item.get("id")
            if mid:
                forget(url, scope, mid, headers=headers)
    return store(url, scope, "active-handoff", text, headers=headers)


def recall(url, scope, query, limit=RECALL_LIMIT, headers=None):
    """Search WITH ISOLATION: the demon searches in the GLOBAL pool (namespace does not filter),
    so we take a wide top and leave ONLY the facts of the requested `scope` by marker
    in content; remove the marker from the text. Unlabeled facts (legacy) — cut."""
    res = http_post_json(f"{url}/agentmemory/search",
                         {"query": query, "namespace": scope, "limit": limit}, headers=headers)
    results = res.get("results", []) if isinstance(res, dict) else []
    out = []
    for r in results:
        obs = r.get("observation") or {}
        raw = (obs.get("narrative") or obs.get("title")
               or " ".join(obs.get("facts") or []))
        sc, text = split_scope(raw)
        if sc != scope:           # alien scope or untagged legacy → isolate
            continue
        out.append({"score": r.get("score"), "text": text, "id": obs.get("id")})
    # Saturation: the demon returned exactly all candidate-pool (common to all projects) — relevant
    # facts scope might not have hit the window. Let us know to narrow down your request./raise the limit.
    if len(results) >= limit:
        warn(f"recall: candidate-pool is saturated ({limit}) — part of the facts scope '{scope}' could "
             f"won't fit; narrow your request or raise it limit.")
    return out


def forget(url, scope, key, headers=None):
    """Delete fact by memoryId: POST /agentmemory/forget {memoryId}.

    agentmemory 0.9.x is waiting EXACTLY `memoryId` (id memory is globally unique);
    former payload {namespace, id} gave HTTP 400 (verified alive curl to the daemon).
    scope is stored in the signature for call compatibility, but is not included in the request.
    """
    try:
        return http_post_json(f"{url}/agentmemory/forget", {"memoryId": key}, headers=headers)
    except HTTPUnauthorizedError:
        raise
    except RuntimeError as e:
        raise RuntimeError(f"forget: {e}") from e


def export(url, scope, headers=None, *, timeout=MEMORY_HEAVY_TIMEOUT_S, retries=MEMORY_RETRIES):
    """Memory dump scope: GET /agentmemory/memories?namespace= (entire GLOBAL pool -
    namespace demon ignores). Most expensive call per channel (SessionStart-digest
    pulls it whole, research/06 §4) — custom timeout/retrays (measured:
    ); retracts (read, not a mutation)."""
    def _do():
        return http_get_json(f"{url}/agentmemory/memories?namespace={quote(scope)}",
                             timeout=timeout, headers=headers)
    res = _retry_read(_do, retries=retries)
    return res.get("memories", []) if isinstance(res, dict) else []


def memory_owner_scope(url, memory_id, scopes, headers=None):
    """Best-effort: scope-fact owner `memory_id` among `scopes` — by marker
    `[[s:<scope>]]` in content (but there is no marker → to the bucket in which it was found), or None,
    if the fact is not found in any scope. Needed forget'at: memoryId is globally unique,
    the demon deletes it without regard to scope, therefore, before deleting, we confirm that
    fact actually belongs to an authorized project (cross-protectionnamespace
    removal). Resistant to dump element shape (raw `content` or observation)."""
    for sc in scopes:
        for m in export(url, sc, headers):
            if str(m.get("id")) != str(memory_id):
                continue
            obs = m.get("observation") or m
            raw = (m.get("content") or obs.get("narrative") or obs.get("title")
                   or " ".join(obs.get("facts") or []))
            marker, _ = split_scope(raw)
            return marker or sc
    return None


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_memory(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind memory <start|run|stop|status|remember|recall|forget|count|digest> ...")
        return
    sub, rest = argv[0], argv[1:]
    config, _src = load_config(env)
    if sub == "start":
        start(env, config)
    elif sub == "run":
        run_foreground(env, config)  # foreground for systemd (exec, not returned)
    elif sub == "stop":
        stop(env, config)
    elif sub == "status":
        _cmd_status(env, config, rest)
    elif sub == "remember":
        _cmd_remember(env, config, rest)
    elif sub == "recall":
        _cmd_recall(env, config, rest)
    elif sub == "forget":
        _cmd_forget(env, config, rest)
    elif sub == "count":
        _cmd_count(env, config, rest)
    elif sub == "digest":
        _cmd_digest(env, config, rest)
    else:
        die(f"unknown subcommand memory: {sub} "
            "(start|stop|status|remember|recall|forget|count|digest)")


# ── memory: scope-aware CLI (single path for hook and person) ─────────────────
# remember/recall/forget believe scope from the project config via namespaces.py —
# same source of truth as MCP and seed. Memory hook delegates here (modes/maind.sh),
# therefore «remembered» (hook) and «remembered» (MCP/CLI) are guaranteed to go to one side.
def _memory_target(env, config, opts):
    """(project|None, write_scopes, read_scopes). --scope = raw-mode without project."""
    from .namespaces import find as ns_find
    from .namespaces import group_scopes, private_scope, recall_scopes
    from .projects import match_cwd
    raw = opts.get("scope")
    if raw:
        return None, [raw], [raw]
    pid = opts.get("project")
    if pid:
        proj = ns_find(config, pid)
        if not proj:
            die(f"project not found in config.json: {pid}")
    else:
        proj = match_cwd(env, config)
        if not proj:
            die("does not define project from cwd — specify --project <id> or --scope <scope>")
    write = [private_scope(proj)]
    if opts.get("share"):                 # --share → also to the general buckets of the group (ns:<tag>)
        for s in group_scopes(proj):
            if s not in write:
                write.append(s)
    return proj, write, recall_scopes(proj)


def _require_daemon(env, config):
    """(url, headers) — headers carries bearer, if the secret is configured (ADR-0001)."""
    _, _, url = resolve_ports(env, config)
    if not health(url):
        die(f"memory daemon not running ({url}) — raise: maind start --only memory")
    return url, auth_headers(resolve_secret(env, config))


def _cmd_remember(env, config, argv):
    opts, pos = parse_args(argv, {"--project": "str", "--scope": "str", "--share": "bool",
                                  "--type": "str", "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print('maind memory remember [--project ID | --scope S] [--share] [--type T] "<fact>"')
        return
    url, headers = _require_daemon(env, config)
    _proj, write_scopes, _read = _memory_target(env, config, opts)
    key = opts.get("type") or "fact"
    written = []
    for sc in write_scopes:
        try:
            res = store_managed(url, sc, key, pos[0], headers=headers)
        except ValueError as e:
            die(str(e))
        mid = (res.get("memory") or {}).get("id") if isinstance(res, dict) else None
        written.append({"scope": sc, "id": mid})
    if opts["json"]:
        print(json.dumps({"written": written}, ensure_ascii=False))
    else:
        print("memory(maind): recorded → " + ", ".join(w["scope"] for w in written))


def _cmd_recall(env, config, argv):
    opts, pos = parse_args(argv, {"--project": "str", "--scope": "str",
                                  "--limit": "str", "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print('maind memory recall [--project ID | --scope S] [--limit N] "<request>"')
        return
    try:
        limit = int(opts.get("limit") or 10)
    except (TypeError, ValueError):
        limit = 10
    url, headers = _require_daemon(env, config)
    _proj, _write, read_scopes = _memory_target(env, config, opts)
    seen, merged = set(), []
    for sc in read_scopes:                # union private + ns:<tag> + global
        for r in recall(url, sc, pos[0], headers=headers):
            text = r.get("text")          # one fact that surfaced in several times. scope'ah - time
            if text in seen:
                continue
            seen.add(text)
            merged.append({**r, "scope": sc})
    merged.sort(key=lambda r: r.get("score") or 0, reverse=True)
    merged = merged[:limit]
    if opts["json"]:
        print(json.dumps(merged, ensure_ascii=False))
    elif not merged:
        print("memory(maind): nothing found")
    else:
        for r in merged:
            print(f"— [{r.get('score')}] {r.get('text')}  ({r.get('scope')})")


def _cmd_forget(env, config, argv):
    opts, pos = parse_args(argv, {"--project": "str", "--scope": "str",
                                  "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print("maind memory forget [--project ID] <memoryId>   # id memory is globally unique")
        return
    url, headers = _require_daemon(env, config)
    res = forget(url, None, pos[0], headers=headers)
    if opts["json"]:
        print(json.dumps(res, ensure_ascii=False))
    else:
        deleted = res.get("deleted") if isinstance(res, dict) else None
        print(f"memory(maind): forget {pos[0]} → deleted={deleted}")


def _truncate_item(text, max_chars):
    """Trim `text` to `max_chars` by last space + suffix DIGEST_TRUNCATE_SUFFIX.
    Doesn't cut in the middle of a word (except for the degenerate case - the suffix itself does not fit into max_chars)."""
    if len(text) <= max_chars:
        return text
    room = max_chars - len(DIGEST_TRUNCATE_SUFFIX)
    if room <= 0:
        return text[:max_chars]
    cut = text[:room]
    sp = cut.rfind(" ")
    if sp > 0:
        cut = cut[:sp]
    return cut + DIGEST_TRUNCATE_SUFFIX


def select_digest_items(raw, private, want, *, limit, budget_chars, item_max_chars, shared_max):
    """Pure function (without I/O/Env) — selection of facts for SessionStart-digest from raw
    memory dump `raw` (list dict export()-forms: content/narrative/title + timestamp|updatedAt|createdAt;
    records with isLatest=false are skipped).

    `private` — private scope project (first in search results); `want` — visible scope's
    (private + ns:*/global by recall_scopes). Algorithm:
    1) filter by scope-token/want + dedup + ecosystem-link cross-ref (as before) →
       partition private_rows/shared_rows, each sorted fresh-from-top;
    2) candidates = all private + shared[:shared_max] (default shared_max=0 → shared not
       participates at all - project-only digest, D10);
    3) each candidate is trimmed to item_max_chars (by word + suffix);
    4) accumulate until budget_chars: overflowing item is trimmed to the remaining budget,
       if the remainder ≥ DIGEST_MIN_TAIL_CHARS, otherwise - drops;
    5) final - count-cap `limit`;
    6) returns (items, dropped) — dropped = how many facts from the visible pool (private+shared,
       excluding cap'and before that) was not included in the total (cut off entirely/limit/budget).

    Returns (items: list[str], dropped: int)."""
    seen, priv_rows, shared_rows = set(), [], []
    for m in raw:
        if m.get("isLatest") is False:      # superseded version — a newer record replaces it
            continue
        text = m.get("content") or m.get("narrative") or m.get("title") or ""
        sc, clean = split_scope(text)
        clean = (clean or "").strip()
        if sc not in want or not clean or clean in seen:
            continue
        # strangers seed-cross-ref's ("[maind:ecosystem-link] a → b") — graph-seeds, no context
        if sc != private and clean.startswith("[maind:ecosystem-link]") and " → " in clean:
            continue
        seen.add(clean)
        # agentmemory 0.9.x dumps updatedAt/createdAt (no `timestamp`); without a key the
        # sort keeps dump order (oldest first) and the digest serves the stalest facts.
        ts = m.get("timestamp") or m.get("updatedAt") or m.get("createdAt") or ""
        (priv_rows if sc == private else shared_rows).append((ts, clean))
    priv_rows.sort(key=lambda r: r[0], reverse=True)     # fresh on top
    shared_rows.sort(key=lambda r: r[0], reverse=True)
    total_pool = len(priv_rows) + len(shared_rows)
    shared_cap = shared_rows[:shared_max] if shared_max > 0 else []
    candidates = [c for _, c in priv_rows] + [c for _, c in shared_cap]

    items, used = [], 0
    for cand in candidates:
        cand = _truncate_item(cand, item_max_chars)
        if used + len(cand) <= budget_chars:
            items.append(cand)
            used += len(cand)
            continue
        remaining = budget_chars - used
        if remaining >= DIGEST_MIN_TAIL_CHARS:
            items.append(_truncate_item(cand, remaining))
            used = budget_chars
        # otherwise - silently drop (will be taken into account in dropped below), try the next candidate
    items = items[:limit]
    dropped = total_pool - len(items)
    return items, dropped


def _cmd_digest(env, config, argv):
    """Compact project memory digest for SessionStart-hook (additionalContext).
    DETERMINISTIC (not semantics): take ALL the facts scope'ov of the project via list+filter by
    scope-token, priority private, freshest on top, byte budget - by
    default project-only (shared_max=0), shared — explicitly with the flag/config. HOOK-SAFE:
    the demon lay down / scope undefined → silently empty, without die."""
    opts, _ = parse_args(argv, {"--project": "str", "--scope": "str", "--limit": "str",
                                "--budget-chars": "str", "--item-max": "str",
                                "--shared-max": "str", "--json": "bool"}, max_pos=0)
    if opts["help"]:
        print("maind memory digest [--project ID|--scope S] [--limit N] [--budget-chars N] "
              "[--item-max N] [--shared-max N]  # digest for SessionStart")
        return
    dg = (config.get("memory") or {}).get("digest") or {}
    try:
        limit = int(opts.get("limit") or 8)
    except (TypeError, ValueError):
        limit = 8
    try:
        budget_chars = int(opts.get("budget_chars") or dg.get("budget_chars") or DIGEST_BUDGET_CHARS)
    except (TypeError, ValueError):
        budget_chars = DIGEST_BUDGET_CHARS
    try:
        item_max_chars = int(opts.get("item_max") or dg.get("item_max_chars") or DIGEST_ITEM_MAX_CHARS)
    except (TypeError, ValueError):
        item_max_chars = DIGEST_ITEM_MAX_CHARS
    try:
        shared_max = int(opts.get("shared_max") or dg.get("shared_max", DIGEST_SHARED_MAX))
    except (TypeError, ValueError):
        shared_max = DIGEST_SHARED_MAX
    try:
        timeout_s = float(dg.get("timeout_s") or MEMORY_HEAVY_TIMEOUT_S)
    except (TypeError, ValueError):
        timeout_s = MEMORY_HEAVY_TIMEOUT_S
    try:
        retries = int(dg["retries"]) if dg.get("retries") is not None else MEMORY_RETRIES
    except (TypeError, ValueError):
        retries = MEMORY_RETRIES
    _, _, url = resolve_ports(env, config)
    if not health(url):
        return                                   # the demon lay down → quiet (hook-safe)
    try:
        proj, _w, read_scopes = _memory_target(env, config, opts)
    except SystemExit:
        return                                   # scope undefined → quiet
    private = read_scopes[0] if read_scopes else None
    want = set(read_scopes)
    headers = auth_headers(resolve_secret(env, config))
    try:                                         # entire pool (namespace ignore) → filter by marker
        raw = export(url, "", headers, timeout=timeout_s, retries=retries)
    except RuntimeError:
        return
    items, dropped = select_digest_items(raw, private, want, limit=limit,
                                         budget_chars=budget_chars,
                                         item_max_chars=item_max_chars,
                                         shared_max=shared_max)
    if not items:
        return
    if opts["json"]:
        print(json.dumps(items, ensure_ascii=False))
        return
    pid = proj["id"] if proj else (opts.get("scope") or "?")
    print(f"Project memory {pid} (mAInd — details: `maind memory recall \"<topic>\"`):")
    for t in items:
        print(f"- {t}")
    if shared_max == 0:
        # D10: project-only default - cross-project is raised explicitly, not swallowed in digest
        print("  (cross-project: maind memory recall --scope ns:<name> — digest project-only)")
    if dropped > 0:
        print(f"  (+{dropped} facts - maind memory recall)")


def _cmd_count(env, config, argv):
    """How many facts are in the project memory according to scope'am (private + ns:<tag> + global) — observability
    «is the memory full». We count by scope-MARKER in the content, like recall/digest: daemon pool shared and
    namespace does not filter, so export('') gives the entire pool, and the membership scope'y decides the marker
    (otherwise they would count the facts of all ecosystem projects)."""
    opts, _ = parse_args(argv, {"--project": "str", "--scope": "str", "--json": "bool"}, max_pos=0)
    if opts["help"]:
        print("maind memory count [--project ID | --scope S] [--json]  "
              "# how many facts are in memory by scope")
        return
    url, headers = _require_daemon(env, config)
    proj, _write, read_scopes = _memory_target(env, config, opts)
    try:
        raw = export(url, "", headers)            # entire pool (namespace ignore) → filter by marker
    except RuntimeError as e:
        die(f"does not read memory: {e}")
    per = {sc: 0 for sc in read_scopes}
    seen = set()
    for m in raw:
        text = m.get("content") or m.get("narrative") or m.get("title") or ""
        sc, clean = split_scope(text)
        if sc in per:
            per[sc] += 1
            clean = (clean or "").strip()
            if clean:
                seen.add(clean)
    total_unique = len(seen)
    if opts["json"]:
        print(json.dumps({"scopes": per, "total_unique": total_unique}, ensure_ascii=False))
        return
    pid = proj["id"] if proj else (opts.get("scope") or "?")
    parts = ", ".join(f"{sc}={n}" for sc, n in per.items())
    print(f"Project memory {pid}: {parts} (unique {total_unique})")


def _cmd_status(env, config, argv):
    opts, _ = parse_args(argv, {"--json": "bool"})
    st = status(env, config)
    if opts["json"]:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return
    state = "started" if st["running"] else "stopped"
    print(f"Memory: {state} — {st['url']} "
          f"(http :{st['http_port']}, stream :{st['stream_port']})")
    if st["pid"]:
        tail = "" if st["pid_alive"] else "  [pidfile is deprecated]"
        print(f"  pid {st['pid']}{tail}")
    elif st["running"]:
        print("  was not launched via maind (no pidfile)")
    print("  workers: " + ", ".join(f"{w['name']}={w['state']}" for w in st["workers"]))
