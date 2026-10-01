"""Seed-memory: a basic fact about project connections so that memory is immediately «is not empty» and
made it visible that she was GENERAL. The text is generated from derive-column (role related
projects), is written to a private bucket project:<id> + short cross-ref to shared buckets
groups (ns:<name>, wildcard → global) — parity with graph by namespace'am: group facts
visible inside namespace and isolated between. Idempotent: repeat with the same text is not
produces facts (dedup by marker/text)."""
from .common import content_hash
from .memory import health, recall, resolve_ports, store
from .namespaces import memory_namespaces_of, namespaces_of, private_scope, recall_scopes

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
    """Write seed-fact in private bucket project:<id> + cross-ref to shared group buckets
    (ns:<name>, wildcard → global) — is idempotent. The demon lies - skip marked
    (will be recorded on the next sync)."""
    pid = project["id"]
    scope = private_scope(project)
    text = seed_text(env, config, project)
    _, _, url = resolve_ports(env, config)
    if not health(url):
        return {"provisioner": "memory", "id": pid, "status": "skip",
                "changed": False, "detail": "memory daemon not running"}
    existing = [item for item in recall(url, scope, MARKER)
                if (item.get("text") or "").startswith(f"[{MARKER}]")]
    if len(existing) == 1 and existing[0].get("text") == text:
        return {"provisioner": "memory", "id": pid, "status": "ok",
                "changed": False, "state": "fresh", "detail": scope}
    if dry:
        return {"provisioner": "memory", "id": pid, "status": "dry", "changed": False}
    from .memory import forget
    for item in existing:
        if item.get("id"):
            forget(url, scope, item["id"])
    store(url, scope, "ecosystem-link", text)
    return {"provisioner": "memory", "id": pid, "status": "ok", "changed": True,
            "state": "stale" if existing else "absent",
            "detail": scope}
