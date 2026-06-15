"""maind onboard <project> — единый онбординг: скиллы (swissknifeman) + подключение к мозгу.

Оркеструет цепочку: зарегистрировать проект → swissknifeman integrate (скиллы+хуки) →
maind deploy (память+граф) → seed графа. Каждый шаг standalone-safe: нет соседа — шаг
пропускается с предупреждением, онбординг продолжается. integrate идёт ДО deploy/seed,
чтобы к моменту seed уже существовал skills-lock.json."""
import json
import os
from pathlib import Path

from .common import die, parse_args, sanitize
from .config import load_config
from .deploy import deploy_project, mark_deployed
from .graph import open_graph, seed_from_config, seed_skills
from .orchestrate import run_capability
from .projects import get as get_project
from .projects import write_config


def _infer_type(path):
    p = Path(path)
    if (p / ".obsidian").is_dir():
        return "obsidian-vault"
    if (p / "composer.json").is_file():
        return "php-package"
    if (p / "package.json").is_file():
        return "node-package"
    return "unknown"


def _ensure_project(env, config, project_or_path, dry=False):
    """(config, project, created). Новый путь → синтез записи (+ write_config, если не dry)."""
    proj = get_project(config, project_or_path)
    if proj is not None:
        return config, proj, False
    path = Path(os.path.expanduser(project_or_path))
    if not path.is_dir():
        die(f"проект не найден: '{project_or_path}' — ни id в .maind.json, ни каталог")
    pid = sanitize(path.name)
    proj = {"id": pid, "name": path.name, "local_path": str(path), "repo": None,
            "type": _infer_type(path), "enabled": True,
            "memory_scope": f"project:{pid}", "graph_node": True,
            "agents": [], "skills": [], "tags": [], "status": "active", "dependencies": []}
    config["projects"] = list(config.get("projects") or []) + [proj]
    if not dry:
        write_config(env, config)
    return config, proj, True


def onboard(env, config, project_or_path, opts):
    dry = bool(opts.get("dry"))
    steps = []
    config, proj, created = _ensure_project(env, config, project_or_path, dry=dry)
    steps.append({"name": "register", "status": "ok",
                  "detail": f"{'создан' if created else 'найден'} project:{proj['id']}"})

    # 1. swissknifeman integrate — скиллы + хуки (standalone-safe)
    if opts.get("skip_skills"):
        steps.append({"name": "skills", "status": "skipped", "detail": "--skip-skills"})
    else:
        extra = ["--bundle", opts.get("bundle") or "recommended"]
        if opts.get("yes"):
            extra.append("--yes")
        try:
            rc = run_capability(env, config, proj["id"], "skm:integrate", extra, dry=dry)
            steps.append({"name": "skills", "status": "ok" if rc == 0 else "failed",
                          "detail": f"swissknifeman integrate rc={rc}"})
        except SystemExit:
            steps.append({"name": "skills", "status": "skipped",
                          "detail": "swissknifeman недоступен — пропуск"})

    # 2. maind deploy — память + граф (MCP-серверы хаба)
    res = deploy_project(env, config, proj, targets=opts.get("targets") or None,
                         with_graphify=opts.get("with_graphify", False), dry=dry)
    if res is None:
        steps.append({"name": "deploy", "status": "failed", "detail": "нет пути проекта"})
    else:
        steps.append({"name": "deploy", "status": "ok",
                      "detail": f"MCP → {', '.join(res['targets'])} "
                                f"({', '.join(res['servers'])})"})
        if not dry:
            config = mark_deployed(config, proj["id"], res)
            write_config(env, config)

    # 3. seed графа (project · uses→skill из свежего skills-lock · depends_on)
    gstats = {}
    if dry:
        steps.append({"name": "graph", "status": "skipped", "detail": "--dry-run"})
    else:
        g = open_graph(env, config)
        seed_from_config(g, config)
        seed_skills(g, env, config)
        g.save()
        gstats = g.stats()
        steps.append({"name": "graph", "status": "ok",
                      "detail": f"{gstats['nodes']} узлов, {gstats['edges']} рёбер"})

    # 4. опционально brain
    if opts.get("with_brain"):
        try:
            run_capability(env, config, proj["id"], "brain:status", dry=dry)
            steps.append({"name": "brain", "status": "ok", "detail": "brain status"})
        except SystemExit:
            steps.append({"name": "brain", "status": "skipped", "detail": "brain недоступен"})

    return {"project": proj["id"], "created": created, "steps": steps,
            "deployed": res is not None, "graph": gstats}


def cmd_onboard(env, argv):
    o, pos = parse_args(argv, {"--bundle": "str", "--skip-skills": "bool",
                               "--targets": "str", "--with-graphify": "bool",
                               "--with-brain": "bool", "--dry-run": "bool",
                               "--yes": "bool", "--json": "bool"}, max_pos=1)
    if not pos:
        die("использование: maind onboard <project|path> [--bundle B --yes "
            "--with-graphify --with-brain --dry-run]")
    config, _src = load_config(env)
    opts = {"bundle": o["bundle"], "skip_skills": o["skip_skills"], "targets": o["targets"],
            "with_graphify": o["with_graphify"], "with_brain": o["with_brain"],
            "dry": o["dry_run"], "yes": o["yes"]}
    report = onboard(env, config, pos[0], opts)
    if o["json"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(f"Онбординг project:{report['project']} "
          f"({'создан' if report['created'] else 'обновлён'}):")
    for s in report["steps"]:
        mark = {"ok": "✓", "skipped": "○", "failed": "✗"}.get(s["status"], "·")
        print(f"  {mark} {s['name']:<9} {s['detail']}")
