"""Property-граф узла: nodes/edges/neighbors/path/subgraph/stats + node-link JSON.

Движок — чистый stdlib (BFS/кратчайший путь), без сторонних зависимостей. Это примитив
хранения: федерация (federation.py) держит граф на проект поверх этого класса; читать
граф нужно через federation.graph_reader (единый фасад), а не напрямую.

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


def empty_graph(env, config):
    """Пустой in-memory граф (тот же движок), который НЕ читает с диска и не должен
    сохраняться. Используется федерацией для union'а нескольких per-project сторов."""
    g = Graph(env, config)
    g._loaded = True  # запретить load() читать persist_path
    return g


# ── CLI ─────────────────────────────────────────────────────────────────────
def _parse_depth(value, default=1):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _edge_types_opt(opts):
    raw = opts.get("edge_types") or ""
    return [t.strip() for t in raw.split(",") if t.strip()] or None


def _reader(env, config):
    """Единый read-фасад графа (federation.graph_reader); lazy-import против цикла."""
    from .federation import graph_reader
    return graph_reader(env, config)


def cmd_graph(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind graph <query|stats|neighbors|view|derive|rebuild> "
              "[--from ID] [--node ID] [--project ID] [--cross] [--namespace NS] "
              "[--depth N] [--edge-types a,b] [--direction out|in|both] [--all] [--json]")
        return
    # `maind graph --project X` / `maind graph --cross` — короткая форма view
    if argv[0] in ("--project", "--cross"):
        return _cmd_view(env, argv)
    sub, rest = argv[0], argv[1:]
    handlers = {"query": _cmd_query, "stats": _cmd_stats, "neighbors": _cmd_neighbors,
                "view": _cmd_view, "derive": _cmd_derive, "rebuild": _cmd_rebuild}
    handler = handlers.get(sub)
    if handler is None:
        die(f"неизвестная подкоманда graph: {sub} "
            f"(query|stats|neighbors|view|derive|rebuild)")
    handler(env, rest)


def _cmd_view(env, argv):
    """Подграф одного проекта (--project) или весь межпроектный слой (--cross)."""
    from .config import load_config
    from .federation import Federation
    opts, _ = parse_args(argv, {"--project": "str", "--cross": "bool",
                                "--namespace": "str", "--json": "bool"})
    config, _src = load_config(env)
    fed = Federation(env, config)
    if opts["cross"]:
        sub = fed.cross(opts["namespace"] or None)
        label = "межпроектный слой" + (f" [ns {opts['namespace']}]"
                                       if opts["namespace"] else "")
    elif opts["project"]:
        sub = fed.project_view(opts["project"])
        label = f"граф проекта {opts['project']}"
    else:
        die("укажите --project <id> или --cross")
    if opts["json"]:
        print(json.dumps(sub, ensure_ascii=False, indent=2))
        return
    print(f"{label}: {len(sub['nodes'])} узлов, {len(sub['edges'])} рёбер")
    for n in sub["nodes"]:
        name = n["attrs"].get("name", "")
        print(f"  {n['id']:<32} {n['type']:<10} {name}")
    for e in sub["edges"]:
        via = e["attrs"].get("via", "")
        print(f"  {e['src']:<28} —{e['type']}→ {e['dst']}"
              + (f"  [{via}]" if via else ""))


def _cmd_derive(env, argv):
    """Пересобрать графы проектов из источников (composer/Brain/override) + индекс."""
    from .config import load_config
    from .derive import derive_all, derive_project_graph
    from .projects import get as get_project
    opts, _ = parse_args(argv, {"--project": "str", "--all": "bool", "--json": "bool"})
    config, _src = load_config(env)
    if opts["project"]:
        proj = get_project(config, opts["project"])
        if proj is None:
            die(f"проект не найден в config.json: {opts['project']}")
        stats = [derive_project_graph(env, config, proj)]
    else:
        stats = derive_all(env, config)
    if opts["json"]:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return
    for s in stats:
        print(f"  {s['id']:<18} узлов {s['nodes']}, рёбер {s['edges']} "
              f"(code {s['by_via'].get('code', 0)}, doc {s['by_via'].get('doc', 0)}, "
              f"override {s['by_via'].get('override', 0)})")


def _cmd_rebuild(env, argv):
    """Пересобрать только индекс из существующих per-project сторов."""
    from .config import load_config
    from .federation import rebuild_index
    opts, _ = parse_args(argv, {"--json": "bool"})
    config, _src = load_config(env)
    res = rebuild_index(env, config)
    if opts["json"]:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print(f"Индекс пересобран: {res['projects']} проектов, "
          f"{res['cross_edges']} межпроектных рёбер")


def _cmd_query(env, argv):
    from .config import load_config
    opts, _ = parse_args(argv, {"--from": "str", "--depth": "str",
                                "--edge-types": "str", "--direction": "str",
                                "--json": "bool"})
    if not opts["from"]:
        die("укажите --from <node-id> (например project:brain)")
    config, _src = load_config(env)
    res = _reader(env, config).query(
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
    s = _reader(env, config).stats()
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
    nb = _reader(env, config).neighbors(
        opts["node"], _parse_depth(opts["depth"], 1),
        _edge_types_opt(opts), opts["direction"] or "out")
    if opts["json"]:
        print(json.dumps(nb, ensure_ascii=False, indent=2))
        return
    for n in nb:
        print(f"  d{n['distance']}  {n['id']:<28} {n['type']}")
