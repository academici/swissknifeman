"""Миграция в maind: from-brain (.projects.json) и from-agentmemory (.agentmemory).

from-brain   — собирает .maind.json из brain-кэша проектов + материализует граф.
from-agentmemory (alias from-skm) — переносит iii-config.yaml в config/memory/
               с service_name: maind. Перенос НЕдеструктивный — источник не трогаем."""
import re
from pathlib import Path

from .common import confirm, die, parse_args
from .config import load_brain_projects, merge_defaults
from .graph import open_graph, seed_from_config
from .projects import write_config


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
    # материализуем граф: проекты как узлы + связи (общая связь)
    g = seed_from_config(open_graph(env, config), config)
    g.save()
    print(f"импортировано из brain: {len(projects)} проектов → "
          f"{env.default_config.name} + граф ({g.stats()['nodes']} узлов)")


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
