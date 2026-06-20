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
}

# sibling → как найти его лаунчер (env-override · проект в .maind.json · путь · bin).
SIBLINGS = {
    "brain": {"env": "MAIND_BRAIN_BIN", "project_id": "brain",
              "path_key": "vault_path", "bin": "bin/brain"},
    # монорепо academici: лаунчер живёт в подпакете packages/swissknifeman/, а
    # local_path указывает на корень репо (где .git) — отсюда вложенный bin-путь.
    "swissknifeman": {"env": "MAIND_SKM_BIN", "project_id": "swissknifeman",
                      "path_key": "local_path",
                      "bin": "packages/swissknifeman/bin/swissknifeman"},
}


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
    if not root:
        die(f"{which} не найден: добавьте проект '{spec['project_id']}' с {spec['path_key']} "
            f"в .maind.json, или задайте {spec['env']}")
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
            die(f"проект не найден в .maind.json: {project_id}")
        subst = {"project": proj.get("id", project_id),
                 "path": os.path.expanduser(proj.get("local_path") or "")}
    argv = [str(binp)] + [a.format(**subst) for a in template] + list(extra or [])
    if dry:
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
