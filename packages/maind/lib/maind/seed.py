"""Read graph connections and render legacy seed text; automatic seed writes are retired."""
from .common import content_hash
from .memory import resolve_ports
from .namespaces import memory_namespaces_of, namespaces_of, recall_scopes

MARKER = "maind:ecosystem-link"


def linked_projects(env, config, project):
    """Related projects from the project graph (neighbors project:<id> → others project:*)."""
    from .federation import project_graph, store_path
    from pathlib import Path
    if not Path(store_path(env, config, project)).exists():
        return []
    g = project_graph(env, config, project)
    pid = project["id"]
    out = []
    for n in g.neighbors(f"project:{pid}", depth=1, direction="out"):
        if n["id"].startswith("project:"):
            other = n["id"].split(":", 1)[1]
            if other != pid and other not in out:
                out.append(other)
    return sorted(out)


def seed_text(env, config, project):
    """Basic fact about project relationships (with token and hash for dedupe/drift detection)."""
    pid = project["id"]
    name = project.get("name", pid)
    ptype = project.get("type", "unknown")
    http_port, _, _ = resolve_ports(env, config)
    linked = linked_projects(env, config, project)
    parts = [f"[{MARKER}] {name} ({ptype}) — ecosystem node academici."]
    ns = sorted(namespaces_of(project))
    if ns != ["default"]:                    # connections are limited to this(and) namespace
        parts.append("Namespace: " + ", ".join(ns) + ".")
    if linked:
        parts.append("Related: " + ", ".join(linked) + ".")
    parts.append(
        f"Project memory isolated (demon mAInd :{http_port}); main bucket - "
        f"{', '.join(recall_scopes(project))}. Shared areas are only accessible by explicit scope"
        + ((": " + ", ".join(sorted(memory_namespaces_of(project))))
           if memory_namespaces_of(project) else "")
        + f". Contacts: maind graph --project {pid}.")
    body = " ".join(parts)
    return f"{body} #{content_hash(body)}"


def seed_memory(env, config, project, *, dry=False):
    """Compatibility provisioner: topology belongs in config/graph, never working memory."""
    return {"provisioner": "memory", "id": project["id"], "status": "skip",
            "changed": False, "state": "disabled",
            "detail": "connection facts live in config/graph; automatic memory seeds disabled"}
