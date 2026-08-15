"""Migrate into maind from Brain projects or agent-memory configuration.

from-brain builds config.json and materializes the graph. from-agentmemory
copies iii-config.yaml with service_name maind without modifying its source.
"""
import re
from pathlib import Path

from ..common import confirm, die, parse_args
from ..config import load_brain_projects, merge_defaults
from ..projects import write_config


def cmd_migrate(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind migrate <from-brain <.projects.json> | "
              "from-agentmemory <dir>> [--force]")
        return
    sub, rest = argv[0], argv[1:]
    if sub == "from-brain":
        _from_brain(env, rest)
    elif sub in ("from-agentmemory", "from-skm"):
        _from_agentmemory(env, rest)
    else:
        die(f"неизвестная подкоманда migrate: {sub} (from-brain|from-agentmemory)")


def _from_brain(env, argv):
    opts, pos = parse_args(argv, {"--force": "bool"}, max_pos=1)
    if not pos:
        die("укажите путь к brain .projects.json: maind migrate from-brain <path>")
    if env.default_config.exists() and not opts["force"]:
        die(f"{env.default_config.name} уже существует — перезапись только с --force")
    projects = load_brain_projects(pos[0])
    config = merge_defaults({
        "_version": "1",
        "node": {"id": "hub", "name": "Academici Hub", "role": "primary"},
        "projects": projects,
        "integrations": {"brain": {"enabled": True, "projects_sync": True,
                                   "sync_direction": "import",
                                   "path": str(Path(pos[0]).expanduser())}},
    })
    write_config(env, config)
    # Materialize graph stores and index from sources of truth.
    from ..derive import derive_all
    stats = derive_all(env, config)
    nodes = sum(s["nodes"] for s in stats)
    print(f"импортировано из brain: {len(projects)} проектов → "
          f"{env.default_config.name} + граф ({nodes} узлов в {len(stats)} сторах)")


def _from_agentmemory(env, argv):
    opts, pos = parse_args(argv, {"--force": "bool"}, max_pos=1)
    if not pos:
        die("укажите путь к .agentmemory (или iii-config.yaml): "
            "maind migrate from-agentmemory <path>")
    src = Path(pos[0]).expanduser()
    if src.is_dir():
        src = src / "iii-config.yaml"
    if not src.is_file():
        die(f"не найден iii-config.yaml: {src}")
    dst = env.memory_config
    if dst.exists() and not opts["force"]:
        if not confirm(f"{dst} уже существует. Перезаписать?"):
            die("отменено (используйте --force для перезаписи)")
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = _set_service_name(src.read_text(encoding="utf-8"), "maind")
    dst.write_text(text, encoding="utf-8")
    print(f"перенесён iii-config: {src} → {dst} (service_name: maind). "
          f"Источник не изменён.")


def _set_service_name(yaml_text, name):
    if "service_name:" in yaml_text:
        return re.sub(r"service_name:\s*\S+", f"service_name: {name}", yaml_text)
    return yaml_text
