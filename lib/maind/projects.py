"""Реестр проектов узла (надмножество brain .projects.json).

Чтение — из конфига (.maind.json или brain-fallback). Запись — только write_config
(единственный писатель .maind.json). sync_from_brain идемпотентен и сохраняет
maind-only поля (skills/tags/dependencies/agents/repo)."""
import json
import os
from pathlib import Path

from .common import atomic_write_json, die, parse_args, warn
from .config import load_brain_projects, load_config

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
    """Единственный писатель .maind.json (atomic). _version проставляется первым ключом."""
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
        print("maind projects <list|sync> [--json] [--from brain] [--path DIR]")
        return
    sub, rest = argv[0], argv[1:]
    if sub == "list":
        _cmd_list(env, rest)
    elif sub == "sync":
        _cmd_sync(env, rest)
    else:
        die(f"неизвестная подкоманда projects: {sub} (list|sync)")


def _cmd_list(env, argv):
    opts, _ = parse_args(argv, {"--json": "bool"})
    config, source = load_config(env)
    projects = listing(env, config)
    if opts["json"]:
        print(json.dumps(projects, ensure_ascii=False, indent=2))
        return
    if not projects:
        print("проектов нет — создайте .maind.json из .maind.example.json "
              "или `maind projects sync --from brain`")
        return
    print(f"Проекты ({len(projects)}, источник: {source}):")
    for p in projects:
        deps = p.get("dependencies") or []
        tail = f" → deps: {', '.join(deps)}" if deps else ""
        dis = "" if p.get("enabled", True) else " [disabled]"
        ptype = p.get("type") or "-"
        print(f"  {p.get('id', '?'):<18} {ptype:<16} {p.get('status', ''):<9}{dis}{tail}")


def _cmd_sync(env, argv):
    opts, _ = parse_args(argv, {"--from": "str", "--path": "str"})
    if opts["from"] not in ("brain", ""):
        die(f"поддерживается только --from brain (получено: '{opts['from']}')")
    config, _src = load_config(env)
    path = opts["path"] or brain_path(config)
    config, stats = sync_from_brain(env, config, path)
    write_config(env, config)
    print(f"Синк из brain ({path}): +{stats['added']} новых, "
          f"~{stats['updated']} обновлено, всего {stats['total']}. "
          f"Записано в {env.default_config.name}")
