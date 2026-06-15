"""Федерация графов слоя 2 (топология между проектами).

Вместо одного общего graph.db — граф-файл на проект (`data/graphs/<id>.db`, или в репо
проекта при `graph_store=local`) плюс тонкий регенерируемый `_index.db` (только
`project:*`-узлы + межпроектные рёбра). Запрос, пересекающий границу проекта, сшивает
нужные сторы в один in-memory union и гоняет по нему обычный BFS (`graph.Graph`).

Принцип владения: узел ПРИНАДЛЕЖИТ проекту pid, если в сторе pid у него `attrs.project==pid`
(так помечает derive). Конечные узлы рёбер, авто-созданные как заглушки (`add_edge`), не
владеются — их канонический владелец резолвится по индексу. Cross-ребро — то, у которого
владельцы src и dst разные. Индекс держит карту владения (узлы-ссылки) + cross-рёбра, поэтому
регенерируется из per-project сторов и сам по себе не источник истины."""
import os
from pathlib import Path

from .graph import Graph, empty_graph


def _enabled_projects(config):
    return [p for p in (config.get("projects") or []) if p.get("enabled", True)]


def store_path(env, config, project):
    """Путь графа проекта. По умолчанию data/graphs/<id>.db; graph_store=local →
    <local_path>/.maind/graph.db (граф живёт в самом репо проекта)."""
    pid = project["id"]
    if project.get("graph_store") == "local" and project.get("local_path"):
        return Path(os.path.expanduser(project["local_path"])) / ".maind" / "graph.db"
    return env.data_dir / "graphs" / f"{pid}.db"


def index_path(env):
    return env.data_dir / "graphs" / "_index.db"


def project_graph(env, config, project):
    """Загруженный граф одного проекта (примитив graph.Graph над его стором)."""
    return Graph(env, config, path=store_path(env, config, project)).load()


def _merge_into(union, src):
    """Скопировать узлы/рёбра стора src в union-граф (upsert; владеющие attrs выигрывают)."""
    for nid, n in src.nodes.items():
        cur = union.nodes.get(nid)
        # узел с явным project (владелец) перетирает заглушку
        if cur is None or (not cur["attrs"].get("project") and n["attrs"].get("project")):
            union.nodes[nid] = {"type": n["type"], "attrs": dict(n["attrs"])}
    for src_id, dsts in src.adj.items():
        for dst_id, e in dsts.items():
            union._link(src_id, dst_id, e["type"], e["attrs"])


def federated_graph(env, config, projects=None):
    """Union сторов проектов в один in-memory граф (federate-on-read). projects=None → все
    enabled. Возвращает graph.Graph — дальше доступны query/neighbors/path/subgraph/stats."""
    projects = _enabled_projects(config) if projects is None else projects
    union = empty_graph(env, config)
    for p in projects:
        sp = store_path(env, config, p)
        if Path(sp).exists():
            _merge_into(union, Graph(env, config, path=sp).load())
    return union


def _owner(nid, owners):
    """Владелец узла: `project:<x>` всегда принадлежит x (даже внешний/без стора)."""
    if nid.startswith("project:"):
        return nid.split(":", 1)[1]
    return owners.get(nid)


def _owner_map(env, config):
    """node_id → pid (владелец). Скан всех сторов: владелец = стор, где attrs.project==pid."""
    owners = {}
    for p in _enabled_projects(config):
        sp = store_path(env, config, p)
        if not Path(sp).exists():
            continue
        g = Graph(env, config, path=sp).load()
        for nid, n in g.nodes.items():
            if n["attrs"].get("project") == p["id"]:
                owners[nid] = p["id"]
    return owners


def rebuild_index(env, config):
    """Пересобрать _index.db из per-project сторов: все `project:*`-узлы (как ссылки с
    attrs.project) + межпроектные рёбра (владельцы src/dst различны). Регенерируемо.
    Возвращает {projects, cross_edges}."""
    owners = _owner_map(env, config)
    idx = Graph(env, config, path=index_path(env))
    idx._loaded = True  # строим с нуля, не читаем старый индекс
    cross = 0
    for p in _enabled_projects(config):
        sp = store_path(env, config, p)
        if not Path(sp).exists():
            continue
        g = Graph(env, config, path=sp).load()
        for nid, n in g.nodes.items():
            o = _owner(nid, owners)
            if o is not None:
                idx.add_node(nid, n["type"], project=o,
                             name=n["attrs"].get("name", ""), ref=True)
        for src_id, dsts in g.adj.items():
            for dst_id, e in dsts.items():
                so, do = _owner(src_id, owners), _owner(dst_id, owners)
                if so is not None and do is not None and so != do:
                    for nid in (src_id, dst_id):
                        if nid not in idx.nodes:
                            idx.add_node(nid, g.nodes.get(nid, {}).get("type")
                                         or "entity", project=_owner(nid, owners),
                                         ref=True)
                    idx.add_edge(src_id, dst_id, e["type"],
                                 via=e["attrs"].get("via"),
                                 plane=e["attrs"].get("plane"))
                    cross += 1
    idx.save()
    return {"projects": len(_enabled_projects(config)), "cross_edges": cross}


def index_graph(env, config):
    """Только межпроектный слой: `project:*`-узлы + cross-рёбра (для `graph --cross`)."""
    return Graph(env, config, path=index_path(env)).load()


class Federation:
    """Read-фасад поверх per-project сторов, дуктайп-совместимый с graph.Graph по чтению.
    Запросы федерируют (union) релевантные сторы и делегируют обычному BFS."""

    def __init__(self, env, config):
        self.env = env
        self.config = config

    def _union(self):
        return federated_graph(self.env, self.config)

    def query(self, frm, depth=1, edge_types=None, direction="out"):
        return self._union().query(frm, depth, edge_types, direction)

    def neighbors(self, node_id, depth=1, edge_types=None, direction="out"):
        return self._union().neighbors(node_id, depth, edge_types, direction)

    def path(self, src, dst, edge_types=None, direction="out"):
        return self._union().path(src, dst, edge_types, direction)

    def subgraph(self, ids, depth=0, direction="both", edge_types=None):
        return self._union().subgraph(ids, depth, direction, edge_types)

    def project_view(self, pid):
        """Подграф одного проекта: индуцированный по его стору (с исходящими cross-рёбрами)."""
        proj = next((p for p in _enabled_projects(self.config) if p["id"] == pid), None)
        if proj is None:
            return {"directed": True, "nodes": [], "edges": []}
        g = project_graph(self.env, self.config, proj)
        return g.subgraph(list(g.nodes), depth=0)

    def cross(self):
        """Межпроектный слой целиком (узлы project:* + cross-рёбра)."""
        ig = index_graph(self.env, self.config)
        return ig.subgraph(list(ig.nodes), depth=0)

    def stats(self):
        s = self._union().stats()
        s["per_project"] = {
            p["id"]: project_graph(self.env, self.config, p).stats()["nodes"]
            for p in _enabled_projects(self.config)
            if Path(store_path(self.env, self.config, p)).exists()
        }
        ig = index_graph(self.env, self.config)
        s["cross_edges"] = sum(len(d) for d in ig.adj.values())
        return s
