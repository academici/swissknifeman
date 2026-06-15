"""Seed-память: базовый факт о связях проекта, чтобы память сразу была «не пустой» и
делала видимым, что она ОБЩАЯ. Текст генерируется из derive-графа (роль, связанные
проекты), пишется в scope project:<id> + короткий cross-ref в global. Идемпотентно:
повтор с тем же текстом не плодит фактов (дедуп по маркеру/тексту)."""
from .common import content_hash
from .memory import health, recall, resolve_ports, store
from .namespaces import namespaces_of

MARKER = "maind:ecosystem-link"


def _linked_projects(env, config, project):
    """Связанные проекты из графа проекта (соседи project:<id> → другие project:*)."""
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
    """Базовый факт о связях проекта (с маркером и хэшем для дедупа/детекта дрейфа)."""
    pid = project["id"]
    name = project.get("name", pid)
    ptype = project.get("type", "unknown")
    http_port, _, _ = resolve_ports(env, config)
    linked = _linked_projects(env, config, project)
    parts = [f"[{MARKER}] {name} ({ptype}) — узел экосистемы academici."]
    ns = sorted(namespaces_of(project))
    if ns != ["default"]:                    # связи ограничены этим(и) namespace
        parts.append("Namespace: " + ", ".join(ns) + ".")
    if linked:
        parts.append("Связан с: " + ", ".join(linked) + ".")
    parts.append(
        f"Память ОБЩАЯ (демон mAInd :{http_port}); scope этого проекта — project:{pid}; "
        f"факты всей экосистемы — в scope global. Связи: maind graph --project {pid}.")
    body = " ".join(parts)
    return f"{body} #{content_hash(body)}"


def seed_memory(env, config, project, *, dry=False):
    """Записать seed-факт в project:<id> + cross-ref в global (идемпотентно). Демон лежит —
    skip с пометкой (запишется на следующем sync)."""
    pid = project["id"]
    scope = project.get("memory_scope") or f"project:{pid}"
    text = seed_text(env, config, project)
    _, _, url = resolve_ports(env, config)
    if not health(url):
        return {"provisioner": "memory", "id": pid, "status": "skip",
                "changed": False, "detail": "демон памяти не запущен"}
    existing = [r.get("text") for r in recall(url, scope, MARKER)]
    if text in existing:
        return {"provisioner": "memory", "id": pid, "status": "ok",
                "changed": False, "state": "fresh", "detail": scope}
    if dry:
        return {"provisioner": "memory", "id": pid, "status": "dry", "changed": False}
    store(url, scope, "ecosystem-link", text)
    linked = _linked_projects(env, config, project)
    if linked:
        store(url, "global", "ecosystem-link",
              f"[{MARKER}] {pid} → {', '.join(linked)}")
    return {"provisioner": "memory", "id": pid, "status": "ok",
            "changed": True, "state": "stale" if existing else "absent", "detail": scope}
