"""Property-граф узла: nodes/edges/neighbors/path/subgraph/stats + node-link JSON.

Движок по умолчанию (adapter=memory) — чистый stdlib (BFS/кратчайший путь), без
сторонних зависимостей. networkx/graphify — опциональные адаптеры (lazy-import),
выбираются через config.graph.adapter; их отсутствие важно только если выбраны явно.

Узлы именуются '<type>:<key>' (например project:brain) — это даёт бесконфликтную
склейку доменов и позволяет выводить тип узла из id."""
import json
import os
from collections import Counter, deque
from pathlib import Path

from .common import atomic_write_json, die, parse_args
from .constants import EDGE_TYPES, GRAPH_VERSION, NODE_TYPES


def _infer_node_type(node_id):
    """Тип узла из префикса '<type>:<key>'; иначе 'entity'."""
    prefix = node_id.split(":", 1)[0] if ":" in node_id else ""
    return prefix if prefix in NODE_TYPES else "entity"


def _resolve_path(env, persist):
    """persist_path из конфига относительно корня узла; абсолютный — как есть."""
    if not persist:
        return env.graph_db
    p = Path(os.path.expanduser(persist))
    return p if p.is_absolute() else (env.root / p)


class Graph:
    """In-memory property-граф с персистом в node-link JSON (stdlib-движок)."""

    def __init__(self, env, config=None, path=None):
        self.env = env
        persist = ((config or {}).get("graph") or {}).get("persist_path")
        self.db_path = Path(path) if path is not None else _resolve_path(env, persist)
        self.nodes = {}        # id -> {"type":.., "attrs":{..}}
        self.adj = {}          # src -> {dst -> {"type":.., "attrs":{..}}}
        self.radj = {}         # dst -> {src -> edge}  (обратный индекс)
        self._loaded = False

    # ── персист ──────────────────────────────────────────────────────────────
    def load(self):
        if self._loaded:
            return self
        self._loaded = True
        if not self.db_path.exists():
            return self
        try:
            data = json.loads(self.db_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{self.db_path}: битый граф JSON: {e}")
        for n in data.get("nodes", []):
            self.nodes[n["id"]] = {
                "type": n.get("type", _infer_node_type(n["id"])),
                "attrs": n.get("attrs", {}),
            }
        for e in data.get("edges", []):
            self._link(e["src"], e["dst"], e.get("type", "relates_to"),
                       e.get("attrs", {}))
        return self

    def save(self):
        atomic_write_json(self.db_path, self._serialize(), version=GRAPH_VERSION)
        return self

    def _serialize(self):
        nodes = [{"id": nid, "type": n["type"], "attrs": n["attrs"]}
                 for nid, n in sorted(self.nodes.items())]
        edges = []
        for src in sorted(self.adj):
            for dst in sorted(self.adj[src]):
                e = self.adj[src][dst]
                edges.append({"src": src, "dst": dst, "type": e["type"],
                              "attrs": e["attrs"]})
        return {"directed": True, "nodes": nodes, "edges": edges}

    # ── мутации ──────────────────────────────────────────────────────────────
    def add_node(self, node_id, type_=None, **attrs):
        self.load()
        type_ = type_ or _infer_node_type(node_id)
        if type_ not in NODE_TYPES:
            raise ValueError(f"недопустимый тип узла: {type_} "
                             f"(допустимо: {', '.join(sorted(NODE_TYPES))})")
        node = self.nodes.get(node_id)
        if node is None:
            self.nodes[node_id] = {"type": type_, "attrs": dict(attrs)}
        else:
            node["type"] = type_
            node["attrs"].update(attrs)
        return node_id

    def _link(self, src, dst, type_, attrs):
        edge = {"type": type_, "attrs": dict(attrs)}
        self.adj.setdefault(src, {})[dst] = edge
        self.radj.setdefault(dst, {})[src] = edge

    def add_edge(self, src, dst, type_, **attrs):
        self.load()
        if type_ not in EDGE_TYPES:
            raise ValueError(f"недопустимый тип ребра: {type_} "
                             f"(допустимо: {', '.join(sorted(EDGE_TYPES))})")
        for nid in (src, dst):
            if nid not in self.nodes:
                self.add_node(nid, _infer_node_type(nid))
        self._link(src, dst, type_, attrs)
        return (src, dst)

    # ── обход ────────────────────────────────────────────────────────────────
    def _step(self, nid, edge_types, direction):
        if direction in ("out", "both"):
            for dst, e in self.adj.get(nid, {}).items():
                if edge_types is None or e["type"] in edge_types:
                    yield dst
        if direction in ("in", "both"):
            for src, e in self.radj.get(nid, {}).items():
                if edge_types is None or e["type"] in edge_types:
                    yield src

    def neighbors(self, node_id, depth=1, edge_types=None, direction="out"):
        """BFS до глубины depth. Возвращает [{id,type,attrs,distance}] без корня."""
        self.load()
        if node_id not in self.nodes:
            return []
        edge_types = set(edge_types) if edge_types else None
        dist = {node_id: 0}
        q = deque([node_id])
        out = []
        while q:
            cur = q.popleft()
            if dist[cur] >= depth:
                continue
            for nxt in self._step(cur, edge_types, direction):
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    n = self.nodes.get(nxt, {"type": _infer_node_type(nxt), "attrs": {}})
                    out.append({"id": nxt, "type": n["type"], "attrs": n["attrs"],
                                "distance": dist[nxt]})
                    q.append(nxt)
        return out

    def path(self, src, dst, edge_types=None, direction="out"):
        """Кратчайший путь (по числу рёбер) [src..dst] или None."""
        self.load()
        if src not in self.nodes or dst not in self.nodes:
            return None
        if src == dst:
            return [src]
        edge_types = set(edge_types) if edge_types else None
        parent = {src: None}
        q = deque([src])
        while q:
            cur = q.popleft()
            for nxt in self._step(cur, edge_types, direction):
                if nxt not in parent:
                    parent[nxt] = cur
                    if nxt == dst:
                        chain = [dst]
                        while parent[chain[-1]] is not None:
                            chain.append(parent[chain[-1]])
                        return list(reversed(chain))
                    q.append(nxt)
        return None

    def subgraph(self, ids, depth=0, direction="both", edge_types=None):
        """Подграф. depth=0 → индуцированный по ids; depth>0 → BFS-замыкание сначала."""
        self.load()
        selected = {i for i in ids if i in self.nodes}
        if depth > 0:
            for i in list(selected):
                for n in self.neighbors(i, depth, edge_types, direction):
                    selected.add(n["id"])
        nodes = [{"id": i, "type": self.nodes[i]["type"],
                  "attrs": self.nodes[i]["attrs"]} for i in sorted(selected)]
        edges = []
        for src in sorted(selected):
            for dst, e in self.adj.get(src, {}).items():
                if dst in selected:
                    edges.append({"src": src, "dst": dst, "type": e["type"],
                                  "attrs": e["attrs"]})
        return {"directed": True, "nodes": nodes, "edges": edges}

    def stats(self):
        self.load()
        by_node = Counter(n["type"] for n in self.nodes.values())
        by_edge = Counter(e["type"] for d in self.adj.values() for e in d.values())
        degree = Counter()
        for src, d in self.adj.items():
            degree[src] += len(d)
            for dst in d:
                degree[dst] += 1
        return {
            "nodes": len(self.nodes),
            "edges": sum(len(d) for d in self.adj.values()),
            "by_node_type": dict(sorted(by_node.items())),
            "by_edge_type": dict(sorted(by_edge.items())),
            "components": self._components(),
            "max_degree": max(degree.values()) if degree else 0,
        }

    def _components(self):
        """Число слабо-связных компонент (рёбра как ненаправленные)."""
        seen = set()
        comps = 0
        for start in self.nodes:
            if start in seen:
                continue
            comps += 1
            stack = [start]
            seen.add(start)
            while stack:
                cur = stack.pop()
                adjacent = set(self.adj.get(cur, {})) | set(self.radj.get(cur, {}))
                for nxt in adjacent:
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
        return comps

    def query(self, frm, depth=1, edge_types=None, direction="out"):
        """Удобный вызов для CLI/MCP: соседи + метаданные."""
        nb = self.neighbors(frm, depth, edge_types, direction)
        return {"root": frm, "depth": depth, "count": len(nb), "neighbors": nb}


def _require_optional(adapter):
    mod = "graphifyy" if adapter == "graphify" else "networkx"
    try:
        __import__(mod)
    except ImportError:
        die(f"graph.adapter = {adapter}, но пакет '{mod}' не установлен "
            f"(pip install {mod}) — или используйте adapter=memory (stdlib)")


def open_graph(env, config):
    """Выбирает движок графа по config.graph.adapter и возвращает загруженный граф.

    memory   — stdlib-движок (по умолчанию);
    graphify/networkx — требуют установленный пакет (lazy-проверка); generic
        node/edge-операции по-прежнему на stdlib-движке с общим персистом, внешняя
        библиотека доступна для расширенных функций;
    disabled — граф-команды недоступны."""
    adapter = ((config or {}).get("graph") or {}).get("adapter", "memory")
    if adapter == "disabled":
        die("граф отключён (graph.adapter = disabled)")
    if adapter in ("graphify", "networkx"):
        _require_optional(adapter)
    return Graph(env, config).load()


def seed_from_config(g, config):
    """Материализует «общую связь»: проекты → узлы, dependencies → depends_on,
    skills → uses, agents → belongs_to. Идемпотентно (upsert). Возвращает граф."""
    projects = (config or {}).get("projects") or []
    for p in projects:
        if p.get("graph_node", True):
            g.add_node(f"project:{p['id']}", "project", name=p.get("name", p["id"]))
    for p in projects:
        pid = f"project:{p['id']}"
        if pid not in g.nodes:
            continue
        for dep in p.get("dependencies") or []:
            g.add_edge(pid, f"project:{dep}", "depends_on")
        for skill in p.get("skills") or []:
            g.add_edge(pid, f"skill:{skill}", "uses")
        for agent in p.get("agents") or []:
            g.add_edge(f"agent:{agent}", pid, "belongs_to")
    return g


# ── skills_sync: связать swissknifeman/boost в граф из skills-lock.json ──────
_PROVIDERS = ("swissknifeman", "laravel-boost", "brain")


def _lock_skills(project):
    """skills-lock.json проекта → {name: {source, bucket, also_in}} или None."""
    local = project.get("local_path")
    if not local:
        return None
    f = Path(os.path.expanduser(local)) / "skills-lock.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("skills") or {}
    except (json.JSONDecodeError, OSError):
        return None


def _skm_has_project(env, project):
    """Есть ли проект в реестре swissknifeman (~/.swissknifeman/projects.json)."""
    reg = env.home / ".swissknifeman" / "projects.json"
    local = project.get("local_path")
    if not reg.is_file() or not local:
        return False
    try:
        db = json.loads(reg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    target = os.path.realpath(os.path.expanduser(local))
    return any(os.path.realpath(os.path.expanduser(p.get("path", ""))) == target
               for p in db.get("projects", []))


def seed_skills(g, env, config):
    """Материализует скиллы проектов в граф: skill-узлы, project─uses→skill,
    skill─provided_by→tool:<источник>. Без lock — грубый fallback project─uses→tool:swissknifeman
    (если проект есть в реестре skm). Идемпотентно (upsert)."""
    stats = {"projects": 0, "skill_nodes": 0, "edges": 0}
    for p in (config or {}).get("projects") or []:
        pid = f"project:{p['id']}"
        skills = _lock_skills(p)
        if skills is not None:
            g.add_node(pid, "project", name=p.get("name", p["id"]))
            for name, entry in skills.items():
                snode = f"skill:{name}"
                g.add_node(snode, "skill", bucket=entry.get("bucket", ""))
                g.add_edge(pid, snode, "uses")
                stats["edges"] += 1
                for src in [entry.get("source")] + list(entry.get("also_in") or []):
                    if src in _PROVIDERS:
                        g.add_edge(snode, f"tool:{src}", "provided_by")
                        stats["edges"] += 1
                stats["skill_nodes"] += 1
            stats["projects"] += 1
        elif _skm_has_project(env, p):
            g.add_node(pid, "project", name=p.get("name", p["id"]))
            g.add_edge(pid, "tool:swissknifeman", "uses")
            stats["edges"] += 1
            stats["projects"] += 1
    return stats


# ── CLI ─────────────────────────────────────────────────────────────────────
def _parse_depth(value, default=1):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _edge_types_opt(opts):
    raw = opts.get("edge_types") or ""
    return [t.strip() for t in raw.split(",") if t.strip()] or None


def cmd_graph(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind graph <query|stats|neighbors> "
              "[--from ID] [--node ID] [--depth N] [--edge-types a,b] "
              "[--direction out|in|both] [--json]")
        return
    sub, rest = argv[0], argv[1:]
    handlers = {"query": _cmd_query, "stats": _cmd_stats, "neighbors": _cmd_neighbors}
    handler = handlers.get(sub)
    if handler is None:
        die(f"неизвестная подкоманда graph: {sub} (query|stats|neighbors)")
    handler(env, rest)


def _cmd_query(env, argv):
    from .config import load_config
    opts, _ = parse_args(argv, {"--from": "str", "--depth": "str",
                                "--edge-types": "str", "--direction": "str",
                                "--json": "bool"})
    if not opts["from"]:
        die("укажите --from <node-id> (например project:brain)")
    config, _src = load_config(env)
    res = open_graph(env, config).query(
        opts["from"], _parse_depth(opts["depth"], 1),
        _edge_types_opt(opts), opts["direction"] or "out")
    if opts["json"]:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print(f"{res['root']} — соседей в радиусе {res['depth']}: {res['count']}")
    for n in res["neighbors"]:
        name = n["attrs"].get("name", "")
        print(f"  d{n['distance']}  {n['id']:<28} {n['type']:<10} {name}")


def _cmd_stats(env, argv):
    from .config import load_config
    opts, _ = parse_args(argv, {"--json": "bool"})
    config, _src = load_config(env)
    s = open_graph(env, config).stats()
    if opts["json"]:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return
    print(f"Граф: {s['nodes']} узлов, {s['edges']} рёбер, "
          f"{s['components']} компонент(ы), max степень {s['max_degree']}")
    if s["by_node_type"]:
        print("  узлы:  " + ", ".join(f"{k}={v}" for k, v in s["by_node_type"].items()))
    if s["by_edge_type"]:
        print("  рёбра: " + ", ".join(f"{k}={v}" for k, v in s["by_edge_type"].items()))


def _cmd_neighbors(env, argv):
    from .config import load_config
    opts, _ = parse_args(argv, {"--node": "str", "--depth": "str",
                                "--direction": "str", "--edge-types": "str",
                                "--json": "bool"})
    if not opts["node"]:
        die("укажите --node <node-id>")
    config, _src = load_config(env)
    nb = open_graph(env, config).neighbors(
        opts["node"], _parse_depth(opts["depth"], 1),
        _edge_types_opt(opts), opts["direction"] or "out")
    if opts["json"]:
        print(json.dumps(nb, ensure_ascii=False, indent=2))
        return
    for n in nb:
        print(f"  d{n['distance']}  {n['id']:<28} {n['type']}")
