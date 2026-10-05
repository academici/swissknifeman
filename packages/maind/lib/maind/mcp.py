"""maind like MCP-server: stdio JSON-RPC 2.0, newline-delimited JSON (transport MCP).

Exhibits tools on top memory/graph/agents/projects. Launch: `maind mcp [--scope project:<id>]`.
Client connection (.mcp.json): {"command": "<repo>/bin/maind", "args": ["mcp"]}.
Clean stdlib — without MCP SDK. Protocol - in stdout (one line JSON + '\\n', without Content-Length),
logs/errors - in stderr. Server crash resistant: tool error → isError, the loop does not crash."""
import json
import os
import sys

from . import agents as agents_mod
from . import memory as memory_mod
from . import projects as projects_mod
from .common import parse_args
from .config import load_config

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "maind", "version": "0.2.0"}

# Trimming target - BELOW warning-threshold Claude Code (10 000 tokens), and not under the default
# client ceiling (25 000, after which the client itself uploads the response to disk and substitutes
# file-reference — is a client emergency exit, not a server delivery channel, see
#). Token Evaluator - grep-heuristic (stdlib, without
# tokenizer): characters/3.2 — more conservative «characters/4» for Cyrillic+JSON-punctuation
#.
TRIM_TARGET_TOKENS = 10_000
CHARS_PER_TOKEN_ESTIMATE = 3.2


def _graph_reader(env, config):
    """Single read-graph facade (federation is the only layout; disabled → die)."""
    from .federation import graph_reader
    return graph_reader(env, config)

TOOLS = [
    {"name": "maind_memory_store",
     "description": "Store temporary useful context (48h default, 72h maximum, 800 chars). "
                    "Project-private by default. No plan journals, decisions or code/git copies; "
                    "use one active-handoff for continuity.",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string", "description": "e.g. project:brain or global"},
         "key": {"type": "string", "enum": ["context", "blocker", "coordination", "active-handoff"]},
         "ttl_hours": {"type": "number", "exclusiveMinimum": 0, "maximum": 72, "default": 48},
         "value": {"type": "string"}}, "required": ["value"]}},
    {"name": "maind_memory_recall",
     "description": "Search unexpired working context. Default: own project only. "
                    "Shared ns/global requires explicit authorized scope.",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string"}, "query": {"type": "string"}}, "required": ["query"]}},
    {"name": "maind_memory_forget",
     "description": "Delete fact from memory by key/id (best-effort).",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string"}, "key": {"type": "string"}}, "required": ["key"]}},
    {"name": "maind_graph_query",
     "description": "Neighbors of a graph node in radius depth (e.g. from=project:brain).",
     "inputSchema": {"type": "object", "properties": {
         "from": {"type": "string"}, "depth": {"type": "integer"},
         "edge_types": {"type": "string", "description": "separated by commas"}},
         "required": ["from"]}},
    {"name": "maind_graph_neighbors",
     "description": "Node neighbors with traversal direction (out|in|both).",
     "inputSchema": {"type": "object", "properties": {
         "node": {"type": "string"}, "depth": {"type": "integer"},
         "direction": {"type": "string"}}, "required": ["node"]}},
    {"name": "maind_graph_path",
     "description": "Shortest path between two graph nodes (or null, if unreachable).",
     "inputSchema": {"type": "object", "properties": {
         "from": {"type": "string"}, "to": {"type": "string"}},
         "required": ["from", "to"]}},
    {"name": "maind_graph_project",
     "description": "Graph of one project (its nodes + outgoing cross-project edges).",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string", "description": "id project, e.g. flexcrm"}},
         "required": ["project"]}},
    {"name": "maind_memory_links",
     "description": "What the project is connected to: inter-project connections from the graph + him ecosystem-link "
                    "memory from all relevant buckets (project:<id> + ns:<groups> + "
                    "global). Memory should namespace'am: common within the group, between - "
                    "isolated. Optional namespace narrows down the graph traversal.",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string"}, "depth": {"type": "integer"},
         "namespace": {"type": "string", "description": "limit bypass to one namespace"}},
         "required": ["project"]}},
    {"name": "maind_agents_list",
     "description": "List of registered node agents with their status.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "maind_projects_list",
     "description": "List of ecosystem projects (from config.json or brain).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "maind_projects_status",
     "description": "Ecosystem State: Hub (memory/graph/demons) + projects (connection, skills).",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string", "description": "optional - one project"}}}},
]
_TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def _log(msg):
    print(f"[maind mcp] {msg}", file=sys.stderr, flush=True)


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _estimate_tokens(text):
    return len(text) / CHARS_PER_TOKEN_ESTIMATE


def _list_candidates(payload):
    """Top-level lists - candidates for cuts: himself payload (if this is a list) or his
    immediate list values (if payload — dictionary). Top level only: one
    funnels `_content` sufficient for all response forms 11 tools (list - bucket
    entire, limited - there are no lists at all, trimming does not work for them)."""
    if isinstance(payload, list):
        yield (), payload
    elif isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list):
                yield (key,), value


def _with_truncation_receipt(payload, path, trimmed, total_count):
    """Data, not just a flag: `truncated`/`returned_count`/`total_count` + human readable
    interrogation hint - naked `truncated: true` does not clear any of the three silent failures
    truncation. `isError` NOT reused - it's busy
    class «tool error» (`_run_tool`/`_tools_call`)."""
    receipt = {
        "truncated": True,
        "returned_count": len(trimmed),
        "total_count": total_count,
        "hint": ("response truncated by context limit; narrow your request (query/depth/project) "
                 "or request the remainder with a separate call"),
    }
    if path == ():
        return {"items": trimmed, **receipt}
    key = path[0]
    out = dict(payload)
    out[key] = trimmed
    out[f"{key}_truncated"] = receipt
    return out


def _truncate_largest_list(payload, limit_tokens):
    """Trims the largest top-level list to a size that fits the limit, binary
    descending by number of elements (JSON is rebuilt on each sample - lists ≤ a couple hundred
    elements in practice, the price is acceptable). None-candidates (neither payload, nor its meaning
    list) — returns the original payload as is: there are no free bytes for trimming, this
    tail case escalation (Implementation Rules), is not silent data loss."""
    candidates = list(_list_candidates(payload))
    if not candidates:
        return payload
    path, full_list = max(candidates, key=lambda c: len(json.dumps(c[1], ensure_ascii=False)))
    if not full_list:
        return payload
    lo, hi = 0, len(full_list)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        trimmed = full_list[:mid]
        candidate_payload = _with_truncation_receipt(payload, path, trimmed, len(full_list))
        text = json.dumps(candidate_payload, ensure_ascii=False)
        if _estimate_tokens(text) <= limit_tokens:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return _with_truncation_receipt(payload, path, full_list[:best], len(full_list))


def _content(payload, is_error=False):
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    # (1) first lever - remove indent=2 (pure savings without data loss); errors do not touch
    # (are short, they do not need trimming, and the shape is important for readability in logs).
    if not is_error and _estimate_tokens(text) > TRIM_TARGET_TOKENS:
        text = json.dumps(payload, ensure_ascii=False)
        # (3) ceiling with receipt — tail case, only triggered if removal indent
        # was not enough (narrow at the input - the level of strategy selection by the tool, not the funnel).
        if _estimate_tokens(text) > TRIM_TARGET_TOKENS:
            trimmed_payload = _truncate_largest_list(payload, TRIM_TARGET_TOKENS)
            text = json.dumps(trimmed_payload, ensure_ascii=False)
    out = {"content": [{"type": "text", "text": text}]}
    if is_error:
        out["isError"] = True
    return out


def _edge_types(arg):
    return [t.strip() for t in (arg or "").split(",") if t.strip()] or None


def _missing_required(tool, args):
    return [k for k in tool["inputSchema"].get("required", []) if not args.get(k)]


def _recall_union(config, url, scope, query, *, include_related_scopes=False, headers=None):
    """Recall with insulation. Project scope remains private by default.

    Shared scope is only read when explicitly ``scope=ns:<name>``. Parameter
    include_related_scopes is reserved for internal diagnostic calls. Obviously
    requested scope not expanding: public MCP-response
    must contain only records of this scope. Raw/non-design scope → exactly him.
    Deedup by text.

    Priority private vs shared:
    when project:<id>-expansion private scope (recall_scopes()[0]) polled without cap
    (RECALL_LIMIT), a shared-scope's (ns:*/global) — with RECALL_SHARED_LIMIT below RECALL_LIMIT,
    otherwise large ns:<group> (dozens of entries) displaces small private scope project
    (measured: 84-96% response from shared on 6 projects). Explicit scope (not project:) without
    expansion — there is no mouth guard, as before."""
    from .namespaces import find, recall_scopes
    scopes = [scope]
    expanded = False
    if include_related_scopes and isinstance(scope, str) and scope.startswith("project:"):
        proj = find(config, scope.split(":", 1)[1])
        if proj:
            scopes = recall_scopes(proj, include_shared=True)
            expanded = True
    seen, out = set(), []
    for i, sc in enumerate(scopes):
        limit = memory_mod.RECALL_SHARED_LIMIT if expanded and i > 0 else memory_mod.RECALL_LIMIT
        for r in memory_mod.recall(url, sc, query, limit=limit, headers=headers):
            if r.get("text") in seen:
                continue
            seen.add(r.get("text"))
            out.append({**r, "scope": sc})
    return out


def _cross_scope_allowed():
    """Admin/hub mode: explicit env-flag removes isolation (cross-project access)."""
    return bool(os.environ.get("MAIND_MCP_ALLOW_CROSS_SCOPE"))


def _allowed_scopes(config, default_scope):
    """Scope's allowed for this MCP-server. Server pinned to the project
    (`maind mcp --scope project:<id>` — rolls it out like that deploy), limited to buckets
    OWN project: private + ns:<his group> + global (recall_scopes). Non-project
    default (global/hub) or env MAIND_MCP_ALLOW_CROSS_SCOPE → None = without restrictions
    (hub/admin, back-compat). This is a server isolation enforcer namespace: client cannot
    replace scope and read/write/delete someone else's private memory."""
    if _cross_scope_allowed():
        return None
    if not (isinstance(default_scope, str) and default_scope.startswith("project:")):
        return None
    from .namespaces import allowed_memory_scopes, find
    proj = find(config, default_scope.split(":", 1)[1])
    return allowed_memory_scopes(proj) if proj else [default_scope]


def _scope_error(scope, allowed):
    """isError-response if scope out of bounds (allowed=None → without restrictions)."""
    if allowed is not None and scope not in allowed:
        return _content({"error": f"scope '{scope}' is out of scope for this project "
                                  f"(insulation namespace); allowed: {allowed}"}, is_error=True)
    return None


def _node_pid(node):
    """pid from the view graph node 'project:<id>', otherwise None."""
    if isinstance(node, str) and node.startswith("project:"):
        return node.split(":", 1)[1]
    return None


def _project_blocked(config, default_scope, target_pid):
    """Is the server pinned to the project denied access to project data? target_pid:
    True, if projects do not share namespace. Unregistered target → do not cut
    (external node, namespace unknown). Hub mode (allowed=None) → do not cut."""
    if target_pid is None or _cross_scope_allowed():
        return False
    if not (isinstance(default_scope, str) and default_scope.startswith("project:")):
        return False
    from .namespaces import find, shares
    pinned = default_scope.split(":", 1)[1]
    if target_pid == pinned:
        return False
    src, dst = find(config, pinned), find(config, target_pid)
    if src is None or dst is None:
        return False
    return not shares(src, dst)


def _graph_error():
    return _content({"error": "access to the graph of another project is denied "
                              "(insulation namespace)"}, is_error=True)


def _run_tool(env, config, name, args, default_scope):
    if name in ("maind_memory_store", "maind_memory_recall", "maind_memory_forget"):
        _, _, url = memory_mod.resolve_ports(env, config)
        if not memory_mod.health(url):
            return _content({"error": memory_mod.unavailable_message(config, url)}, is_error=True)
        headers = memory_mod.auth_headers(memory_mod.resolve_secret(env, config))
        requested_scope = args.get("scope")
        scope = requested_scope or default_scope
        allowed = _allowed_scopes(config, default_scope)
        denied = _scope_error(scope, allowed)
        if denied:
            return denied
        if name == "maind_memory_store":
            return _content(memory_mod.store_managed(
                url, scope, args.get("key", "context"), args["value"], headers=headers,
                ttl_hours=args.get("ttl_hours", 48), source="mcp"))
        if name == "maind_memory_recall":
            return _content(_recall_union(config, url, scope, args["query"],
                                          include_related_scopes=False,
                                          headers=headers))
        # forget: scope-arg is allowed, but memoryId global - confirm ownership by token,
        # otherwise the client would delete someone else's fact according to the known id, without going beyond your scope.
        if allowed is not None:
            owner = memory_mod.memory_owner_scope(url, args["key"], allowed, headers)
            if owner is None or owner not in allowed:
                return _content({"error": "forget rejected: fact not allowed "
                                          "scope of this project (insulation namespace)"},
                                is_error=True)
        return _content(memory_mod.forget(url, scope, args["key"], headers=headers))
    if name == "maind_graph_query":
        if _project_blocked(config, default_scope, _node_pid(args["from"])):
            return _graph_error()
        # namespace is declared in the schema, but USED to be silently ignored → bypass federated ALL
        # projects (alien nodes namespace leaked to depth>1, although the starting node was gated).
        # Now let's narrow it down union to the requested namespace (starting node is still under _project_blocked).
        res = _graph_reader(env, config).query(args["from"], int(args.get("depth", 1)),
                                               _edge_types(args.get("edge_types")),
                                               namespace=args.get("namespace"))
        return _content(res)
    if name == "maind_graph_neighbors":
        if _project_blocked(config, default_scope, _node_pid(args["node"])):
            return _graph_error()
        res = _graph_reader(env, config).neighbors(args["node"], int(args.get("depth", 1)),
                                                   None, args.get("direction", "out"),
                                                   namespace=args.get("namespace"))
        return _content(res)
    if name == "maind_graph_path":
        if (_project_blocked(config, default_scope, _node_pid(args["from"]))
                or _project_blocked(config, default_scope, _node_pid(args["to"]))):
            return _graph_error()
        res = _graph_reader(env, config).path(args["from"], args["to"])
        return _content({"from": args["from"], "to": args["to"], "path": res})
    if name == "maind_graph_project":
        if _project_blocked(config, default_scope, args["project"]):
            return _graph_error()
        from .federation import Federation
        return _content(Federation(env, config).project_view(args["project"]))
    if name == "maind_memory_links":
        if _project_blocked(config, default_scope, args["project"]):
            return _graph_error()
        from .federation import Federation
        from .namespaces import find, recall_scopes
        pid = args["project"]
        links = Federation(env, config).query(f"project:{pid}", int(args.get("depth", 1)),
                                              namespace=args.get("namespace") or None)
        proj = find(config, pid) or {"id": pid}
        _, _, url = memory_mod.resolve_ports(env, config)
        mem = []
        if memory_mod.health(url):
            for sc in recall_scopes(proj, include_shared=bool(args.get("namespace"))):
                for r in memory_mod.recall(url, sc, "maind:ecosystem-link"):
                    mem.append({**r, "scope": sc})
        return _content({"project": pid, "graph": links, "memory": mem})
    if name == "maind_agents_list":
        return _content(agents_mod.listing(env, config))
    if name == "maind_projects_list":
        return _content(projects_mod.listing(env, config))
    if name == "maind_projects_status":
        from .probe import probe_hub, probe_project
        hub = probe_hub(env, config)
        reach = hub["memory"]["running"]
        projs = projects_mod.listing(env, config)
        if args.get("project"):
            projs = [p for p in projs if p.get("id") == args["project"]]
        reports = [probe_project(env, config, p, memory_reachable=reach) for p in projs]
        return _content({"hub": hub, "projects": reports})
    return _content({"error": f"tool not implemented: {name}"}, is_error=True)


def _tools_call(env, config, name, args, default_scope):
    args = args or {}
    missing = _missing_required(_TOOLS_BY_NAME[name], args)
    if missing:
        return _content({"error": f"required argument is missing: {', '.join(missing)}"}, is_error=True)
    try:
        return _run_tool(env, config, name, args, default_scope)
    except SystemExit as e:               # die() inside the tool (e.g. graph is disabled)
        return _content({"error": f"tool not available: {e}"}, is_error=True)
    except Exception as e:                 # any tool error - do not crash the server
        # Logging the KEYS of the arguments (are not values - they can contain memory contents/secrets)
        _log(f"tool error {name} args={sorted(args)}: {e!r}")
        return _content({"error": f"tool error: {e}"}, is_error=True)


def dispatch(env, config, req, default_scope="global"):
    """JSON-RPC routing. Returns the response or None (for notifications)."""
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        params = req.get("params") or {}
        version = params.get("protocolVersion") or PROTOCOL_VERSION
        return _result(req_id, {"protocolVersion": version,
                                "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        if name not in _TOOLS_BY_NAME:
            return _error(req_id, -32601, f"unknown tool: {name}")
        return _result(req_id, _tools_call(env, config, name, params.get("arguments"),
                                           default_scope))
    if method == "ping":
        return _result(req_id, {})
    if req_id is None:
        return None  # unknown notification - ignore
    return _error(req_id, -32601, f"unknown method: {method}")


# ── framing: newline-delimited JSON (stdio-transport MCP) ───────────────────
# MCP stdio: each JSON-RPC message - one line, ends '\n', without
# embedded-line breaks and WITHOUT Content-Length headers (this is not LSP).
def read_message(stream):
    """Reads one NDJSON-message. EOF → None. Empty lines are skipped."""
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if line:
            return json.loads(line.decode("utf-8"))


def write_message(stream, obj):
    stream.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    stream.flush()


def serve(env, config, stdin=None, stdout=None, default_scope="global"):
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    debug = bool(os.environ.get("MAIND_MCP_DEBUG"))
    _log(f"start: {len(TOOLS)} tools, scope default {default_scope}")
    while True:
        try:
            req = read_message(stdin)
        except (json.JSONDecodeError, ValueError) as e:
            _log(f"broken message skipped: {e}")
            continue
        if req is None:
            break
        if debug:
            _log(f"→ {req.get('method')} (id={req.get('id')})")
        try:
            resp = dispatch(env, config, req, default_scope)
        except (SystemExit, Exception) as e:   # the last milestone - don't drop the loop
            _log(f"exception in dispatch: {e!r}")
            resp = _error(req.get("id"), -32603, f"internal error: {e}") \
                if req.get("id") is not None else None
        if resp is not None:
            write_message(stdout, resp)
    _log("stop (EOF)")


def _default_scope_from_cwd(env, config):
    """Defaultscope, when there is no explicit --scope/MAIND_SCOPE: project:<id> by cwd, otherwise global.
    Safer than the former deaf 'global': argless-the server writes to the bucket of HIS project, and not to
    general global (futgun - early miss cwd ⇒ memory leaked into shared-layer)."""
    from .namespaces import private_scope
    from .constants import GLOBAL_SCOPE
    proj = projects_mod.match_cwd(env, config)
    return private_scope(proj) if proj else GLOBAL_SCOPE


def cmd_mcp(env, argv):
    opts, _ = parse_args(argv, {"--scope": "str"})
    config, _src = load_config(env)
    default_scope = (opts["scope"] or os.environ.get("MAIND_SCOPE")
                     or _default_scope_from_cwd(env, config))
    serve(env, config, default_scope=default_scope)
