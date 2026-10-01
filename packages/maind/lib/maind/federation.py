"""Layer 2 Graph Federation (topology between projects).

Instead of one general graph.db — graph file for the project (`data/graphs/<id>.db`, or in the repo
project when `graph_store=local`) plus thin regenerable `_index.db` (only
`project:*`-nodes + cross-project edges). Request crossing project boundary stitches
necessary stores in one in-memory union and drives the usual BFS (`graph.Graph`).

Ownership principle: the node BELONGS to the project pid, if in the store pid he has `attrs.project==pid`
(so marks derive). Edge end nodes auto-generated as stubs (`add_edge`), not
are owned - their canonical owner is resolved by index. Cross-edge - the one with
owners src and dst different. Index holds the ownership card (link nodes) + cross-edges, so
is regenerated from The per-project story is not in itself a source of truth."""
import os
from pathlib import Path

from .common import die
from .graph import Graph, empty_graph
from .namespaces import in_namespace, shares


def _enabled_projects(config):
    return [p for p in (config.get("projects") or []) if p.get("enabled", True)]


def graph_disabled(config):
    """Graph disabled (adapter=disabled)?"""
    return ((config or {}).get("graph") or {}).get("adapter") == "disabled"


def graph_reader(env, config):
    """Single read-graph topology façade: federation is the only layout.
    Ductype compatible graph.Graph by reading (query/neighbors/path/subgraph/stats).
    adapter=disabled → die. Used CLI/MCP/probe/status — without engine selection duplicates."""
    if graph_disabled(config):
        die("graph disabled (graph.adapter = disabled)")
    return Federation(env, config)


def _owners_share_ns(so, do, pmap):
    """Do owning projects share namespace. Unknown owner (external node, no
    records) → True: namespace unknown, cross-save the edge (like derive.link_allowed)."""
    a, b = pmap.get(so), pmap.get(do)
    return True if a is None or b is None else shares(a, b)


def store_path(env, config, project):
    """Project graph path. Default data/graphs/<id>.db; graph_store=local →
    <local_path>/.maind/graph.db (the graph lives in the project repo itself)."""
    pid = project["id"]
    if project.get("graph_store") == "local" and project.get("local_path"):
        return Path(os.path.expanduser(project["local_path"])) / ".maind" / "graph.db"
    return env.data_dir / "graphs" / f"{pid}.db"


def index_path(env):
    return env.data_dir / "graphs" / "_index.db"


def project_graph(env, config, project):
    """Loaded graph of one project (primitive graph.Graph over his store)."""
    return Graph(env, config, path=store_path(env, config, project)).load()


def _merge_into(union, src):
    """Copy nodes/store edges src in union-graph (upsert; owning attrs win)."""
    for nid, n in src.nodes.items():
        cur = union.nodes.get(nid)
        # node with explicit project (owner) grinds the plug
        if cur is None or (not cur["attrs"].get("project") and n["attrs"].get("project")):
            union.nodes[nid] = {"type": n["type"], "attrs": dict(n["attrs"])}
    for src_id, dsts in src.adj.items():
        for dst_id, e in dsts.items():
            union._link(src_id, dst_id, e["type"], e["attrs"])


def federated_graph(env, config, projects=None):
    """Union project stores in one in-memory graph (federate-on-read). projects=None → all
    enabled. Returns graph.Graph — further available query/neighbors/path/subgraph/stats."""
    projects = _enabled_projects(config) if projects is None else projects
    union = empty_graph(env, config)
    for p in projects:
        sp = store_path(env, config, p)
        if Path(sp).exists():
            _merge_into(union, Graph(env, config, path=sp).load())
    return union


def _owner(nid, owners):
    """Node owner: `project:<x>` always belongs x (even external/without store)."""
    if nid.startswith("project:"):
        return nid.split(":", 1)[1]
    return owners.get(nid)


def _owner_map(env, config):
    """node_id → pid (owner). Scan of all stores: owner = store, where attrs.project==pid."""
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
    """Rebuild _index.db from per-project stores: all `project:*`-nodes (as links with
    attrs.project) + cross-project edges (owners src/dst are different). Regenerable.
    Returns {projects, cross_edges}."""
    owners = _owner_map(env, config)
    pmap = {p["id"]: p for p in _enabled_projects(config)}
    idx = Graph(env, config, path=index_path(env))
    idx._loaded = True  # building from scratch, not reading the old index
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
                # defense-in-depth: inter-namespace cross-edge is not indexed
                # (in case of outdated/local stores that did not pass derive-gate)
                if (so is not None and do is not None and so != do
                        and _owners_share_ns(so, do, pmap)):
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
    """Cross-project layer only: `project:*`-nodes + cross-ribs (for `graph --cross`)."""
    return Graph(env, config, path=index_path(env)).load()


class Federation:
    """Read-facade on top per-project store, ducttype-compatible graph.Graph on reading.
    Queries are federated (union) relevant stores and delegate to the usual BFS."""

    def __init__(self, env, config):
        self.env = env
        self.config = config
        self._union_cache = {}   # namespace → union-graph (instance is short-lived, read-only)

    def _union(self, namespace=None):
        if namespace in self._union_cache:
            return self._union_cache[namespace]
        projects = None
        if namespace:
            projects = [p for p in _enabled_projects(self.config)
                        if in_namespace(p, namespace)]
        union = federated_graph(self.env, self.config, projects)
        self._union_cache[namespace] = union
        return union

    def query(self, frm, depth=1, edge_types=None, direction="out", namespace=None):
        return self._union(namespace).query(frm, depth, edge_types, direction)

    def neighbors(self, node_id, depth=1, edge_types=None, direction="out", namespace=None):
        return self._union(namespace).neighbors(node_id, depth, edge_types, direction)

    def path(self, src, dst, edge_types=None, direction="out", namespace=None):
        return self._union(namespace).path(src, dst, edge_types, direction)

    def subgraph(self, ids, depth=0, direction="both", edge_types=None):
        return self._union().subgraph(ids, depth, direction, edge_types)

    def project_view(self, pid):
        """Subgraph of one project: induced by its side (with outgoing cross-edges)."""
        proj = next((p for p in _enabled_projects(self.config) if p["id"] == pid), None)
        if proj is None:
            return {"directed": True, "nodes": [], "edges": []}
        g = project_graph(self.env, self.config, proj)
        return g.subgraph(list(g.nodes), depth=0)

    def cross(self, namespace=None):
        """Cross-project layer (nodes project:* + cross-ribs). namespace → nodes only
        projects of this namespace (wildcard-projects fall into any namespace)."""
        ig = index_graph(self.env, self.config)
        ids = list(ig.nodes)
        if namespace:
            pmap = {p["id"]: p for p in _enabled_projects(self.config)}
            ids = [nid for nid in ids
                   if (pmap.get(ig.nodes[nid]["attrs"].get("project")) is not None
                       and in_namespace(pmap[ig.nodes[nid]["attrs"]["project"]], namespace))]
        return ig.subgraph(ids, depth=0)

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
