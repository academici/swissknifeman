"""maind как MCP-сервер: stdio JSON-RPC 2.0, newline-delimited JSON (транспорт MCP).

Экспонирует tools поверх memory/graph/agents/projects. Запуск: `maind mcp [--scope project:<id>]`.
Подключение клиента (.mcp.json): {"command": "<repo>/bin/maind", "args": ["mcp"]}.
Чистый stdlib — без MCP SDK. Протокол — в stdout (одна строка JSON + '\\n', без Content-Length),
логи/ошибки — в stderr. Сервер крэш-устойчив: ошибка инструмента → isError, цикл не падает."""
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


def _graph_reader(env, config):
    """Единый read-фасад графа (федерация — единственная раскладка; disabled → die)."""
    from .federation import graph_reader
    return graph_reader(env, config)

TOOLS = [
    {"name": "maind_memory_store",
     "description": "Сохранить факт в долгосрочную память (scope=namespace; по умолчанию — scope узла).",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string", "description": "напр. project:brain или global"},
         "key": {"type": "string", "description": "категория факта (type)"},
         "value": {"type": "string"}}, "required": ["value"]}},
    {"name": "maind_memory_recall",
     "description": "Поиск по долгосрочной памяти в scope (по умолчанию — scope узла).",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string"}, "query": {"type": "string"}}, "required": ["query"]}},
    {"name": "maind_memory_forget",
     "description": "Удалить факт из памяти по ключу/id (best-effort).",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string"}, "key": {"type": "string"}}, "required": ["key"]}},
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
    {"name": "maind_graph_path",
     "description": "Кратчайший путь между двумя узлами графа (или null, если недостижим).",
     "inputSchema": {"type": "object", "properties": {
         "from": {"type": "string"}, "to": {"type": "string"}},
         "required": ["from", "to"]}},
    {"name": "maind_graph_project",
     "description": "Граф одного проекта (его узлы + исходящие межпроектные рёбра).",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string", "description": "id проекта, напр. flexcrm"}},
         "required": ["project"]}},
    {"name": "maind_memory_links",
     "description": "С чем связан проект: межпроектные связи из графа + его ecosystem-link "
                    "память из всех релевантных бакетов (project:<id> + ns:<группы> + "
                    "global). Память следует namespace'ам: внутри группы общая, между — "
                    "изолирована. Необязательный namespace сужает обход графа.",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string"}, "depth": {"type": "integer"},
         "namespace": {"type": "string", "description": "ограничить обход одним namespace"}},
         "required": ["project"]}},
    {"name": "maind_agents_list",
     "description": "Список зарегистрированных агентов узла с их состоянием.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "maind_projects_list",
     "description": "Список проектов экосистемы (из config.json или brain).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "maind_projects_status",
     "description": "Состояние экосистемы: хаб (память/граф/демоны) + проекты (подключение, скиллы).",
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string", "description": "необязательно — один проект"}}}},
]
_TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def _log(msg):
    print(f"[maind mcp] {msg}", file=sys.stderr, flush=True)


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


def _missing_required(tool, args):
    return [k for k in tool["inputSchema"].get("required", []) if not args.get(k)]


def _recall_union(config, url, scope, query):
    """Recall с изоляцией + объединением scope'ов проекта: project:<id> разворачивается в
    приватный + ns:<группы> + global (recall_scopes), чтобы Claude видел и приватную, и
    общую-по-тегу память. Сырой/непроектный scope → ровно он. Дедуп по тексту."""
    from .namespaces import find, recall_scopes
    scopes = [scope]
    if isinstance(scope, str) and scope.startswith("project:"):
        proj = find(config, scope.split(":", 1)[1])
        if proj:
            scopes = recall_scopes(proj)
    seen, out = set(), []
    for sc in scopes:
        for r in memory_mod.recall(url, sc, query):
            if r.get("text") in seen:
                continue
            seen.add(r.get("text"))
            out.append({**r, "scope": sc})
    return out


def _cross_scope_allowed():
    """Админ/хаб-режим: явный env-флаг снимает изоляцию (кросс-проектный доступ)."""
    return bool(os.environ.get("MAIND_MCP_ALLOW_CROSS_SCOPE"))


def _allowed_scopes(config, default_scope):
    """Scope'ы, разрешённые этому MCP-серверу. Сервер, запинненный к проекту
    (`maind mcp --scope project:<id>` — так его раскатывает deploy), ограничен бакетами
    СВОЕГО проекта: приватный + ns:<его группы> + global (recall_scopes). Не-project
    default (global/хаб) или env MAIND_MCP_ALLOW_CROSS_SCOPE → None = без ограничений
    (хаб/админ, back-compat). Это серверный энфорс изоляции namespace: клиент не может
    подменить scope и прочитать/записать/удалить чужую приватную память."""
    if _cross_scope_allowed():
        return None
    if not (isinstance(default_scope, str) and default_scope.startswith("project:")):
        return None
    from .namespaces import find, recall_scopes
    proj = find(config, default_scope.split(":", 1)[1])
    return recall_scopes(proj) if proj else [default_scope]


def _scope_error(scope, allowed):
    """isError-ответ, если scope вне разрешённых (allowed=None → без ограничений)."""
    if allowed is not None and scope not in allowed:
        return _content({"error": f"scope '{scope}' вне разрешённых для этого проекта "
                                  f"(изоляция namespace); разрешено: {allowed}"}, is_error=True)
    return None


def _node_pid(node):
    """pid из узла графа вида 'project:<id>', иначе None."""
    if isinstance(node, str) and node.startswith("project:"):
        return node.split(":", 1)[1]
    return None


def _project_blocked(config, default_scope, target_pid):
    """Запрещён ли запинненному к проекту серверу доступ к данным проекта target_pid:
    True, если проекты не делят namespace. Незарегистрированный target → не режем
    (внешний узел, namespace неизвестен). Хаб-режим (allowed=None) → не режем."""
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
    return _content({"error": "доступ к графу другого проекта запрещён "
                              "(изоляция namespace)"}, is_error=True)


def _run_tool(env, config, name, args, default_scope):
    if name in ("maind_memory_store", "maind_memory_recall", "maind_memory_forget"):
        _, _, url = memory_mod.resolve_ports(env, config)
        if not memory_mod.health(url):
            return _content({"error": "демон памяти не запущен (maind start --only memory)"},
                            is_error=True)
        scope = args.get("scope") or default_scope
        allowed = _allowed_scopes(config, default_scope)
        denied = _scope_error(scope, allowed)
        if denied:
            return denied
        if name == "maind_memory_store":
            return _content(memory_mod.store(url, scope, args.get("key", "fact"), args["value"]))
        if name == "maind_memory_recall":
            return _content(_recall_union(config, url, scope, args["query"]))
        # forget: scope-арг разрешён, но memoryId глобален — подтверждаем владение по маркеру,
        # иначе клиент удалил бы чужой факт по известному id, не выходя за свой scope.
        if allowed is not None:
            owner = memory_mod.memory_owner_scope(url, args["key"], allowed)
            if owner is None or owner not in allowed:
                return _content({"error": "forget отклонён: факт не принадлежит разрешённым "
                                          "scope этого проекта (изоляция namespace)"},
                                is_error=True)
        return _content(memory_mod.forget(url, scope, args["key"]))
    if name == "maind_graph_query":
        if _project_blocked(config, default_scope, _node_pid(args["from"])):
            return _graph_error()
        # namespace объявлен в схеме, но РАНЬШЕ молча игнорировался → обход федерировал ВСЕ
        # проекты (узлы чужих namespace утекали на depth>1, хотя стартовый узел гейтился).
        # Теперь сужаем union до запрошенного namespace (стартовый узел по-прежнему под _project_blocked).
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
            for sc in recall_scopes(proj):   # project:<id> + ns:<группы> + global
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
    return _content({"error": f"инструмент не реализован: {name}"}, is_error=True)


def _tools_call(env, config, name, args, default_scope):
    args = args or {}
    missing = _missing_required(_TOOLS_BY_NAME[name], args)
    if missing:
        return _content({"error": f"не хватает аргументов: {', '.join(missing)}"}, is_error=True)
    try:
        return _run_tool(env, config, name, args, default_scope)
    except SystemExit as e:               # die() внутри инструмента (напр. граф отключён)
        return _content({"error": f"инструмент недоступен: {e}"}, is_error=True)
    except Exception as e:                 # любая ошибка инструмента — не роняем сервер
        # Логируем КЛЮЧИ аргументов (не значения — в них может быть содержимое памяти/секреты)
        _log(f"ошибка инструмента {name} args={sorted(args)}: {e!r}")
        return _content({"error": f"ошибка инструмента: {e}"}, is_error=True)


def dispatch(env, config, req, default_scope="global"):
    """JSON-RPC роутинг. Возвращает ответ или None (для нотификаций)."""
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
            return _error(req_id, -32601, f"неизвестный инструмент: {name}")
        return _result(req_id, _tools_call(env, config, name, params.get("arguments"),
                                           default_scope))
    if method == "ping":
        return _result(req_id, {})
    if req_id is None:
        return None  # неизвестная нотификация — игнорируем
    return _error(req_id, -32601, f"неизвестный метод: {method}")


# ── framing: newline-delimited JSON (stdio-транспорт MCP) ───────────────────
# MCP stdio: каждое JSON-RPC сообщение — одна строка, оканчивается '\n', без
# embedded-переводов строки и БЕЗ Content-Length заголовков (это не LSP).
def read_message(stream):
    """Читает одно NDJSON-сообщение. EOF → None. Пустые строки пропускаются."""
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
    _log(f"старт: {len(TOOLS)} tools, scope по умолчанию {default_scope}")
    while True:
        try:
            req = read_message(stdin)
        except (json.JSONDecodeError, ValueError) as e:
            _log(f"битое сообщение пропущено: {e}")
            continue
        if req is None:
            break
        if debug:
            _log(f"→ {req.get('method')} (id={req.get('id')})")
        try:
            resp = dispatch(env, config, req, default_scope)
        except (SystemExit, Exception) as e:   # последний рубеж — не роняем цикл
            _log(f"исключение в dispatch: {e!r}")
            resp = _error(req.get("id"), -32603, f"внутренняя ошибка: {e}") \
                if req.get("id") is not None else None
        if resp is not None:
            write_message(stdout, resp)
    _log("стоп (EOF)")


def _default_scope_from_cwd(env, config):
    """Дефолт-scope, когда нет явного --scope/MAIND_SCOPE: project:<id> по cwd, иначе global.
    Безопаснее прежнего глухого 'global': argless-сервер пишет в бакет СВОЕГО проекта, а не в
    общий global (футган — раньше промах cwd ⇒ память утекала в shared-слой)."""
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
