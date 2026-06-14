"""maind как MCP-сервер: stdio JSON-RPC 2.0 (LSP-style Content-Length framing).

Экспонирует 6 tools поверх memory/graph/agents/projects. Запуск: `maind mcp`.
Подключение клиента (.mcp.json):
  {"command": "<repo>/bin/maind", "args": ["mcp"]}
Чистый stdlib — без MCP SDK. Логи/предупреждения идут в stderr, протокол — в stdout."""
import json
import sys

from . import agents as agents_mod
from . import memory as memory_mod
from . import projects as projects_mod
from .config import load_config
from .graph import open_graph

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "maind", "version": "0.1.0"}

TOOLS = [
    {"name": "maind_memory_store",
     "description": "Сохранить факт в долгосрочную память узла (scope = namespace).",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string", "description": "напр. project:brain или global"},
         "key": {"type": "string", "description": "категория факта (type)"},
         "value": {"type": "string"}}, "required": ["scope", "value"]}},
    {"name": "maind_memory_recall",
     "description": "Поиск по долгосрочной памяти в заданном scope.",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string"}, "query": {"type": "string"}},
         "required": ["scope", "query"]}},
    {"name": "maind_graph_query",
     "description": "Соседи узла графа в радиусе depth (напр. from=project:brain).",
     "inputSchema": {"type": "object", "properties": {
         "from": {"type": "string"}, "depth": {"type": "integer"},
         "edge_types": {"type": "string", "description": "через запятую"}},
         "required": ["from"]}},
    {"name": "maind_graph_neighbors",
     "description": "Соседи узла с направлением обхода (out|in|both).",
     "inputSchema": {"type": "object", "properties": {
         "node": {"type": "string"}, "depth": {"type": "integer"},
         "direction": {"type": "string"}}, "required": ["node"]}},
    {"name": "maind_agents_list",
     "description": "Список зарегистрированных агентов узла с их состоянием.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "maind_projects_list",
     "description": "Список проектов экосистемы (из .maind.json или brain).",
     "inputSchema": {"type": "object", "properties": {}}},
]
_TOOL_NAMES = {t["name"] for t in TOOLS}


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _content(payload, is_error=False):
    out = {"content": [{"type": "text",
                        "text": json.dumps(payload, ensure_ascii=False, indent=2)}]}
    if is_error:
        out["isError"] = True
    return out


def _edge_types(arg):
    return [t.strip() for t in (arg or "").split(",") if t.strip()] or None


def _tools_call(env, config, name, args):
    args = args or {}
    if name in ("maind_memory_store", "maind_memory_recall"):
        _, _, url = memory_mod.resolve_ports(env, config)
        if not memory_mod.health(url):
            return _content({"error": "демон памяти не запущен (maind start --only memory)"},
                            is_error=True)
        if name == "maind_memory_store":
            return _content(memory_mod.store(url, args.get("scope", "global"),
                                             args.get("key", "fact"),
                                             args.get("value", "")))
        return _content(memory_mod.recall(url, args.get("scope", "global"),
                                          args.get("query", "")))
    if name == "maind_graph_query":
        res = open_graph(env, config).query(
            args.get("from", ""), int(args.get("depth", 1)),
            _edge_types(args.get("edge_types")))
        return _content(res)
    if name == "maind_graph_neighbors":
        res = open_graph(env, config).neighbors(
            args.get("node", ""), int(args.get("depth", 1)),
            None, args.get("direction", "out"))
        return _content(res)
    if name == "maind_agents_list":
        return _content(agents_mod.listing(env, config))
    if name == "maind_projects_list":
        return _content(projects_mod.listing(env, config))
    return _content({"error": f"инструмент не реализован: {name}"}, is_error=True)


def dispatch(env, config, req):
    """JSON-RPC роутинг. Возвращает ответ или None (для нотификаций)."""
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        return _result(req_id, {"protocolVersion": PROTOCOL_VERSION,
                                "capabilities": {"tools": {}},
                                "serverInfo": SERVER_INFO})
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        if name not in _TOOL_NAMES:
            return _error(req_id, -32601, f"неизвестный инструмент: {name}")
        return _result(req_id, _tools_call(env, config, name, params.get("arguments")))
    if method == "ping":
        return _result(req_id, {})
    if req_id is None:
        return None  # неизвестная нотификация — игнорируем
    return _error(req_id, -32601, f"неизвестный метод: {method}")


# ── framing ──────────────────────────────────────────────────────────────────
def read_message(stream):
    """Читает одно Content-Length-framed сообщение из бинарного потока. EOF → None."""
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.decode("ascii", "replace").strip()
        if line == "":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    length = int(headers.get("content-length", 0))
    if length <= 0:
        return None
    return json.loads(stream.read(length).decode("utf-8"))


def write_message(stream, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


def serve(env, config, stdin=None, stdout=None):
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    while True:
        try:
            req = read_message(stdin)
        except (json.JSONDecodeError, ValueError):
            continue
        if req is None:
            break
        resp = dispatch(env, config, req)
        if resp is not None:
            write_message(stdout, resp)


def cmd_mcp(env, argv):
    config, _src = load_config(env)
    serve(env, config)
