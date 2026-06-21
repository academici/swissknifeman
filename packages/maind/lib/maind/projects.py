"""Реестр проектов узла (надмножество brain .projects.json).

Чтение — из конфига (config.json или brain-fallback). Запись — только write_config
(единственный писатель config.json). sync_from_brain идемпотентен и сохраняет
maind-only поля (skills/tags/dependencies/agents/repo)."""
import json
import os
from pathlib import Path

from .common import atomic_write_json, die, parse_args, warn
from .config import load_brain_projects, load_config
from .namespaces import in_namespace, namespaces_of

# Поля, которые обновляются из brain при синке (остальное — maind-only, сохраняем).
BRAIN_SOURCED = ("name", "local_path", "vault_path", "type", "enabled", "docs_folders")


def listing(env, config):
    """Список проектов из конфига (как есть)."""
    return list(config.get("projects") or [])


def get(config, project_id):
    for p in config.get("projects") or []:
        if p.get("id") == project_id:
            return p
    return None


def sync_from_brain(env, config, brain_path):
    """Импорт/обновление проектов из brain .projects.json. Идемпотентно, мерджит по
    id. Возвращает (config, stats); config НЕ записывается (это делает write_config)."""
    incoming = load_brain_projects(brain_path)
    existing = {p.get("id"): p for p in (config.get("projects") or [])}
    order = [p.get("id") for p in (config.get("projects") or [])]
    added = updated = 0
    for inc in incoming:
        pid = inc["id"]
        if pid in existing:
            cur = existing[pid]
            for f in BRAIN_SOURCED:
                if inc.get(f) is not None:
                    cur[f] = inc[f]
            updated += 1
        else:
            existing[pid] = inc
            order.append(pid)
            added += 1
        lp = inc.get("local_path")
        if lp and not Path(os.path.expanduser(lp)).exists():
            warn(f"проект '{pid}': локальный путь не найден — {lp}")
    config["projects"] = [existing[pid] for pid in order]
    return config, {"added": added, "updated": updated, "total": len(existing)}


def write_config(env, config):
    """Единственный писатель config.json (atomic). _version проставляется первым ключом."""
    out = {"_version": str(config.get("_version", "1"))}
    out.update({k: v for k, v in config.items() if k != "_version"})
    atomic_write_json(env.default_config, out)


def brain_path(config):
    """Где искать brain .projects.json: integrations.brain.path → vault проекта brain
    → дефолт ~/Vaults/Brain."""
    integ = (config.get("integrations") or {}).get("brain") or {}
    p = integ.get("path") or integ.get("local_path")
    if p:
        return p
    for proj in config.get("projects") or []:
        if proj.get("id") == "brain" and proj.get("vault_path"):
            return proj["vault_path"]
    return os.path.expanduser("~/Vaults/Brain")


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_projects(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind projects <list|status|sync> [--json] [--project ID] "
              "[--namespace NS] [--from brain] [--path DIR]")
        return
    sub, rest = argv[0], argv[1:]
    if sub == "list":
        _cmd_list(env, rest)
    elif sub == "status":
        _cmd_status(env, rest)
    elif sub == "sync":
        _cmd_sync(env, rest)
    else:
        die(f"неизвестная подкоманда projects: {sub} (list|status|sync)")


def _cmd_status(env, argv):
    from .probe import probe_hub, probe_project
    from .workspace import trusted_dirs
    opts, _ = parse_args(argv, {"--json": "bool", "--project": "str", "--all": "bool",
                                "--namespace": "str"})
    config, _src = load_config(env)
    hub = probe_hub(env, config)
    reach = hub["memory"]["running"]
    trusted = trusted_dirs(env)
    projs = listing(env, config)
    if opts["project"]:
        projs = [p for p in projs if p.get("id") == opts["project"]]
    if opts["namespace"]:
        projs = [p for p in projs if in_namespace(p, opts["namespace"])]
    reports = [probe_project(env, config, p, memory_reachable=reach, trusted=trusted)
               for p in projs]
    snapshot = {"hub": hub, "projects": reports}
    if opts["json"]:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return
    m, g, dw = hub["memory"], hub["graph"], hub["docs_watcher"]
    print(f"Хаб: память {'up' if m['running'] else 'down'} ({m['url']}) · "
          f"граф {g['nodes']}n/{g['edges']}e · docs-watcher "
          f"{'up' if dw['running'] else 'down'}")
    print(f"Проекты ({len(reports)}):")
    for r in reports:
        c = r.get("configured", {})
        mcp = ("a" if c.get("agentmemory_mcp") else "-") \
            + ("m" if c.get("maind_mcp") else "-") \
            + ("c" if c.get("code_mcp") else "-")
        sk = r.get("skills", {}).get("total", 0)
        trust = "trust✓" if r.get("trusted") else "trust·"
        print(f"  {r['status']:<11} {r['id']:<18} mcp[{mcp}] {trust} skills={sk:<3} "
              f"{r.get('memory_scope', '')}")


def _cmd_list(env, argv):
    opts, _ = parse_args(argv, {"--json": "bool", "--namespace": "str"})
    config, source = load_config(env)
    projects = listing(env, config)
    if opts["namespace"]:
        projects = [p for p in projects if in_namespace(p, opts["namespace"])]
    if opts["json"]:
        print(json.dumps(projects, ensure_ascii=False, indent=2))
        return
    if not projects:
        print("проектов нет — создайте config.json из config.example.json "
              "или `maind projects sync --from brain`")
        return
    print(f"Проекты ({len(projects)}, источник: {source}):")
    for p in projects:
        deps = p.get("dependencies") or []
        tail = f" → deps: {', '.join(deps)}" if deps else ""
        ns = ", ".join(sorted(namespaces_of(p)))
        dis = "" if p.get("enabled", True) else " [disabled]"
        ptype = p.get("type") or "-"
        print(f"  {p.get('id', '?'):<18} {ptype:<16} {p.get('status', ''):<9}"
              f"ns[{ns}]{dis}{tail}")


# ── namespaces ───────────────────────────────────────────────────────────────
def cmd_namespaces(env, argv):
    """Список namespace экосистемы: реестр (секция namespaces) + проекты-члены.
    Источник членства — поле projects[].namespaces (нет/пусто → 'default')."""
    opts, _ = parse_args(argv, {"--json": "bool"})
    if opts["help"]:
        print("maind namespaces [--json]  — namespace-группы и их проекты-члены")
        return
    config, _src = load_config(env)
    registry = config.get("namespaces") or {}
    projs = listing(env, config)
    members = {}                              # ns → [project ids] (без wildcard)
    wildcard = []                            # проекты '*' — во всех namespace
    for p in projs:
        ns = namespaces_of(p)
        if "*" in ns:
            wildcard.append(p["id"])
            continue
        for n in ns:
            members.setdefault(n, []).append(p["id"])
    names = sorted(set(members) | set(registry) | {"default"})
    if opts["json"]:
        out = {n: {"meta": registry.get(n, {}),
                   "members": sorted(members.get(n, [])), "wildcard": sorted(wildcard)}
               for n in names}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"Namespaces ({len(names)}):")
    for n in names:
        meta = registry.get(n) or {}
        title = f" — {meta['name']}" if meta.get("name") else ""
        mem = sorted(members.get(n, []))
        print(f"  {n:<16}{title}")
        print(f"    члены: {', '.join(mem) if mem else '—'}")
    if wildcard:
        print(f"  {'*':<16} — общая инфраструктура (во всех namespace)")
        print(f"    члены: {', '.join(sorted(wildcard))}")


def _cmd_sync(env, argv):
    opts, _ = parse_args(argv, {"--from": "str", "--path": "str"})
    src = opts["from"] or "brain"
    config, _src = load_config(env)
    if src == "brain":
        path = opts["path"] or brain_path(config)
        config, stats = sync_from_brain(env, config, path)
        write_config(env, config)
        print(f"Синк из brain ({path}): +{stats['added']} новых, "
              f"~{stats['updated']} обновлено, всего {stats['total']}. "
              f"Записано в {env.default_config.name}")
    elif src == "swissknifeman":
        from .derive import derive_all
        stats = derive_all(env, config)
        edges = sum(s["by_via"]["skills"] for s in stats)
        print(f"Derive скиллов (федерация): {len(stats)} проектов, "
              f"{edges} скилл-рёбер → графы проектов")
    else:
        die(f"--from: brain | swissknifeman (получено: '{src}')")
