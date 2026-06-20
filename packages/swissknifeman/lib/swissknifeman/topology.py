"""topology — глобальная карта локальной среды (~/.swissknifeman/topology.json).

Три узла-хаба: brain (docs-hub), swissknifeman (skills-hub), projects_base
(workspace). Конфиг живёт в $HOME, машинно-специфичен (как .projects.json у
Brain) и НЕ коммитится в проекты. Команда читает/создаёт его; раздаваемый скилл
skills/system/local-topology объясняет схему и резолвит узлы по этому файлу.

Подкоманды:
  init   интерактивно собрать конфиг (авто-детект дефолтов, промпт на каждый узел)
  show   напечатать топологию (человекочитаемо или --json)
"""
import json
import os
import shutil
import sys
from pathlib import Path

from .common import die, now_iso, parse_flags, warn
from .state import load_db

TOPOLOGY_VERSION = 1

# Роли узлов фиксированы — конфиг описывает ГДЕ они, а не ЧТО они.
ROLES = {
    "brain": "docs-hub",
    "swissknifeman": "skills-hub",
    "projects_base": "workspace",
}


# --- I/O ----------------------------------------------------------------------
def load_topology(env, quiet=False):
    """Прочитать topology.json. None — если файла нет/он битый."""
    f = env.topology_file
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        if not quiet:
            warn(f"{f} повреждён (невалидный JSON) — пересоздайте: "
                 "swissknifeman topology init")
        return None
    if data.get("version", 1) > TOPOLOGY_VERSION:
        die(f"{f} записан более новой версией swissknifeman — обновите реестр "
            "(git pull) и перезапустите install.sh")
    return data


def save_topology(env, data):
    """Атомарная запись с бэкапом существующего в *.json.bak."""
    env.state_dir.mkdir(parents=True, exist_ok=True)
    f = env.topology_file
    if f.exists():
        shutil.copy2(f, f.with_suffix(".json.bak"))
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, f)


# --- detection ----------------------------------------------------------------
def detect_projects_base(env):
    """Общий предок путей из projects.json; иначе дефолт ~/projects."""
    try:
        paths = [p["path"] for p in load_db(env).get("projects", [])
                 if p.get("path")]
        if len(paths) >= 2:
            common = os.path.commonpath(paths)
            if common and common != os.sep:
                return common
    except (OSError, ValueError):
        pass
    return str(env.home / "projects")


def detect_brain(env):
    """Конвенциональный путь ~/Vaults/Brain — предлагается как дефолт."""
    return str(env.home / "Vaults" / "Brain")


def _norm(path):
    path = (path or "").strip()
    return os.path.abspath(os.path.expanduser(path)) if path else ""


def _build(nodes):
    return {key: {"path": _norm(nodes.get(key, "")), "role": role}
            for key, role in ROLES.items()}


# --- subcommands --------------------------------------------------------------
def _prompt(label, default, interactive):
    if not interactive:
        return default
    suffix = f" [{default}]" if default else ""
    return input(f"{label}{suffix}: ").strip() or default


def _show_data(data):
    print(f"Топология (версия {data.get('version', '?')}):")
    for key, node in data.get("nodes", {}).items():
        print(f"  {key:14}{node.get('path', '')}  ({node.get('role', '')})")


def _cmd_show(env, as_json):
    data = load_topology(env)
    if data is None:
        print("Топология не настроена. Создать: swissknifeman topology init")
        return
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        _show_data(data)


def _cmd_init(env, opts):
    existing = load_topology(env, quiet=True) or {}
    prev = existing.get("nodes", {})

    def default_for(key, flag, detect):
        return (opts.get(flag) or prev.get(key, {}).get("path")
                or detect)

    brain = default_for("brain", "brain", detect_brain(env))
    skman = default_for("swissknifeman", "swissknifeman", str(env.root))
    base = default_for("projects_base", "projects_base", detect_projects_base(env))

    interactive = sys.stdin.isatty() and not opts.get("yes")
    if interactive:
        print("Настройка топологии (Enter — оставить значение по умолчанию):")
    brain = _prompt("  Brain-волт (docs-hub)", brain, interactive)
    skman = _prompt("  swissknifeman (skills-hub)", skman, interactive)
    base = _prompt("  база проектов (workspace)", base, interactive)

    data = {
        "version": TOPOLOGY_VERSION,
        "nodes": _build({"brain": brain, "swissknifeman": skman,
                         "projects_base": base}),
        "created_at": existing.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    save_topology(env, data)
    print(f"Записано: {env.topology_file}")
    _show_data(data)


def cmd_topology(env, argv):
    argv = list(argv)
    sub = argv.pop(0) if argv and not argv[0].startswith("-") else "show"
    opts = parse_flags(argv, {
        "--json": "bool", "--brain": "str", "--swissknifeman": "str",
        "--projects-base": "str", "--yes": "bool",
    })
    if opts["help"]:
        print("swissknifeman topology <init|show> [--json] [--brain PATH] "
              "[--swissknifeman PATH] [--projects-base PATH] [--yes]")
        return
    if sub == "init":
        _cmd_init(env, opts)
    elif sub == "show":
        _cmd_show(env, as_json=opts["json"])
    else:
        die(f"неизвестная подкоманда topology: {sub} (ожидается init|show)")
