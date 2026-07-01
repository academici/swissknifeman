"""maind run — оркестрация: дёргать внутренние команды соседних пакетов из одной точки.

Командный пункт: maind не переписывает функционал brain/swissknifeman, а делегирует им
по белому списку возможностей (CAPABILITIES). Лаунчеры соседей сами находят свой корень,
поэтому достаточно абсолютного пути к bin + аргументы. Никакого shell=True — только argv-список."""
import os
import subprocess
import sys
from pathlib import Path

from .common import die, parse_args
from .config import load_config
from .constants import SIBLINGS
from .projects import get as get_project

# Белый список: name → (sibling, argv-шаблон, needs_project). {project}=id, {path}=local_path.
CAPABILITIES = {
    "brain:sync":    ("brain", ["sync", "{project}"], True),
    "brain:status":  ("brain", ["status", "{project}", "--json"], True),
    "brain:list":    ("brain", ["list"], False),
    "skm:vendor":    ("swissknifeman", ["vendor", "--target", "{path}"], True),
    "skm:update":    ("swissknifeman", ["update", "--target", "{path}"], True),
    "skm:lock":      ("swissknifeman", ["lock", "--target", "{path}"], True),
    "skm:integrate": ("swissknifeman", ["integrate", "--target", "{path}"], True),
    "skm:status":    ("swissknifeman", ["status", "--target", "{path}"], True),
    # окружение Claude Code (permissions/MCP/хуки) — пакет harness. skiller integrate
    # уже зовёт harness под капотом; env:* нужны для прямого/гранулярного применения
    # окружения (напр. при onboard --skip-skills) и для router'а зонтика `swissknifeman env`.
    # env:apply — permissions; env:mcp/env:hooks — точечная раскатка MCP-серверов/хуков.
    "env:apply":     ("harness", ["permissions", "--target", "{path}"], True),
    "env:mcp":       ("harness", ["mcp", "--target", "{path}"], True),
    "env:hooks":     ("harness", ["hooks", "--target", "{path}"], True),
    # каталог возможностей intent-router (.claude/agent-router.config.json) из
    # доставленных агентов + локальных скиллов + /task:*; провиженер router-config в sync.
    "env:router":    ("harness", ["router", "--generate", "--target", "{path}"], True),
    # детерминированная доставка пака субагентов (--pack приходит в extra):
    # render --auto резолвит интервью без агента; upgrade — версионный апгрейд.
    "env:agent-pack":         ("harness",
                               ["agent-packs", "render", "--auto", "--target", "{path}"], True),
    "env:agent-pack-upgrade": ("harness",
                               ["agent-packs", "upgrade", "--target", "{path}"], True),
}

# SIBLINGS (как найти лаунчер соседа) — в constants.py (общий с sync, без lazy-импорта).

# Возможности, чей сосед-лаунчер поддерживает СВОЙ `--dry-run` (harness env:*): при dry
# прокидываем флаг и запускаем ПО-НАСТОЯЩЕМУ → честный превью (версии/конфликты пака,
# что реально запишется), а не print+rc0. Для прочих (нет своего dry) — печать намерения.
# Причина: `maind sync --dry-run` давал ложно-зелёный превью апгрейда паков (field-feedback).
DRY_CAPABLE = {"env:apply", "env:mcp", "env:hooks",
               "env:agent-pack", "env:agent-pack-upgrade", "env:router"}


def _sibling_bin(config, which):
    spec = SIBLINGS[which]
    override = os.environ.get(spec["env"])
    if override:
        p = Path(os.path.expanduser(override))
        if not p.exists():
            die(f"{spec['env']}={override} — файл не найден")
        return p
    proj = get_project(config, spec["project_id"])
    root = proj.get(spec["path_key"]) if proj else None
    # brain: если нет записи проекта — резолвим vault так же, как синк (brain_path):
    # integrations.brain.path → vault проекта brain → дефолт ~/Vaults/Brain. brain_path
    # может вернуть путь к файлу .projects.json — нормализуем к каталогу vault (его родитель).
    if not root and which == "brain":
        from .projects import brain_path
        bp = Path(os.path.expanduser(brain_path(config)))
        root = str(bp.parent if bp.name.endswith(".json") else bp)
    if not root:
        die(f"{which} не найден: добавьте проект '{spec['project_id']}' с {spec['path_key']} "
            f"в config.json, или задайте {spec['env']}")
    binp = Path(os.path.expanduser(root)) / spec["bin"]
    if not binp.exists():
        die(f"{which}: лаунчер не найден — {binp}")
    return binp


def run_capability(env, config, project_id, capability, extra=None, *, dry=False):
    """Делегировать возможность соседнему пакету. Возвращает код возврата дочернего процесса."""
    if capability not in CAPABILITIES:
        die(f"неизвестная возможность: {capability}\nдоступно: "
            + ", ".join(sorted(CAPABILITIES)))
    sibling, template, needs_project = CAPABILITIES[capability]
    binp = _sibling_bin(config, sibling)
    subst = {}
    if needs_project:
        proj = get_project(config, project_id)
        if proj is None:
            die(f"проект не найден в config.json: {project_id}")
        subst = {"project": proj.get("id", project_id),
                 "path": os.path.expanduser(proj.get("local_path") or "")}
    argv = [str(binp)] + [a.format(**subst) for a in template] + list(extra or [])
    if dry:
        if capability in DRY_CAPABLE:
            # сосед умеет свой --dry-run → честный превью (реальный rc/конфликты), не rc0
            return subprocess.run(argv + ["--dry-run"], check=False).returncode
        print("[dry-run] " + " ".join(argv))
        return 0
    return subprocess.run(argv, check=False).returncode


def list_capabilities():
    for name in sorted(CAPABILITIES):
        sib, tmpl, _ = CAPABILITIES[name]
        print(f"  {name:<16} {sib}: {' '.join(tmpl)}")


def cmd_run(env, argv):
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    opts, pos = parse_args(argv, {"--list": "bool", "--dry-run": "bool"}, max_pos=2)
    if opts["list"] or (pos[:1] == ["list"]):
        list_capabilities()
        return
    if len(pos) < 2:
        die("использование: maind run <project> <capability> [-- доп.аргументы]\n"
            "список возможностей: maind run --list")
    config, _src = load_config(env)
    rc = run_capability(env, config, pos[0], pos[1], extra, dry=opts["dry_run"])
    if rc:
        sys.exit(rc)
