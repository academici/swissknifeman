"""maind onboard <project> — единый онбординг: скиллы (skiller) + подключение к мозгу.

Оркеструет цепочку: зарегистрировать проект → skiller integrate (скиллы+хуки) →
maind deploy (память+граф) → seed графа. Каждый шаг standalone-safe: нет соседа — шаг
пропускается с предупреждением, онбординг продолжается. integrate идёт ДО deploy/seed,
чтобы к моменту seed уже существовал skills-lock.json."""
import json
import os
from pathlib import Path

from .common import die, parse_args, sanitize
from .config import load_config
from .deploy import deploy_project, mark_deployed
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
        die(f"проект не найден: '{project_or_path}' — ни id в config.json, ни каталог")
    pid = sanitize(path.name)
    proj = {"id": pid, "name": path.name, "local_path": str(path), "repo": None,
            "type": _infer_type(path), "enabled": True,
            "memory_scope": f"project:{pid}",
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

    # 1. skiller integrate — скиллы + хуки (standalone-safe)
    if opts.get("skip_skills"):
        steps.append({"name": "skills", "status": "skipped", "detail": "--skip-skills"})
    else:
        extra = ["--bundle", opts.get("bundle") or "recommended"]
        if opts.get("yes"):
            extra.append("--yes")
        try:
            rc = run_capability(env, config, proj["id"], "skm:integrate", extra, dry=dry)
            steps.append({"name": "skills", "status": "ok" if rc == 0 else "failed",
                          "detail": f"skiller integrate rc={rc}"})
        except SystemExit:
            steps.append({"name": "skills", "status": "skipped",
                          "detail": "skiller недоступен — пропуск"})

    # 2. maind deploy — память + граф (MCP-серверы хаба)
    # --with-code (legacy --with-graphify) фиксируем как намерение в записи проекта, чтобы
    # последующие `maind sync` тоже раскатывали код-граф (config-driven, см. _mcp_run).
    want_code = opts.get("with_code") or opts.get("with_graphify")
    if want_code and not (proj.get("code") or proj.get("graphify")):
        proj["code"] = True
        if not dry:
            write_config(env, config)
    res = deploy_project(env, config, proj, targets=opts.get("targets") or None,
                         with_code=True if want_code else None, dry=dry)
    from . import codegraph
    if codegraph.enabled(proj, codegraph.settings(config)):  # дефолтный .serena/project.yml
        codegraph.apply_serena_config(env, config, proj, "install", dry)
    if res is None:
        steps.append({"name": "deploy", "status": "failed", "detail": "нет пути проекта"})
    else:
        steps.append({"name": "deploy", "status": "ok",
                      "detail": f"MCP → {', '.join(res['targets'])} "
                                f"({', '.join(res['servers'])})"})
        if not dry:
            config = mark_deployed(config, proj["id"], res)
            write_config(env, config)

    # 3. derive графа из источников истины (код/доки/override/skills) → стор проекта + индекс
    gstats = {}
    from .federation import graph_disabled
    if dry:
        steps.append({"name": "graph", "status": "skipped", "detail": "--dry-run"})
    elif graph_disabled(config):
        steps.append({"name": "graph", "status": "skipped", "detail": "граф отключён"})
    else:
        from .derive import derive_project_graph
        from .federation import Federation, rebuild_index
        d = derive_project_graph(env, config, proj)
        rebuild_index(env, config)
        gstats = Federation(env, config).stats()
        steps.append({"name": "graph", "status": "ok",
                      "detail": f"derive {proj['id']}: {d['nodes']} узлов, "
                                f"{d['edges']} рёбер (code {d['by_via']['code']}, "
                                f"doc {d['by_via']['doc']})"})

    # 3b. seed-память: базовый факт о связях (видимость «память общая»)
    if not dry:
        from .seed import seed_memory
        ms = seed_memory(env, config, proj)
        steps.append({"name": "memory", "status": "ok" if ms["status"] == "ok" else "skipped",
                      "detail": ms.get("detail", ms["status"])})

    # 3c. ecosystem-skill: управляемый скилл с инструкцией про MCP-инструменты и связи
    from .skilldoc import apply_ecosystem_skill
    try:
        sk = apply_ecosystem_skill(env, config, proj, "auto", dry)
        steps.append({"name": "skill",
                      "status": "ok" if sk["status"] in ("ok", "dry") else "skipped",
                      "detail": f"ecosystem-mcp ({sk.get('detail', sk['status'])})"})
    except OSError as e:
        steps.append({"name": "skill", "status": "skipped", "detail": f"шаблон недоступен: {e}"})

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
                               "--targets": "str", "--with-code": "bool",
                               "--with-graphify": "bool",
                               "--with-brain": "bool", "--dry-run": "bool",
                               "--yes": "bool", "--json": "bool"}, max_pos=1)
    if not pos:
        die("использование: maind onboard <project|path> [--bundle B --yes "
            "--with-code --with-brain --dry-run]")
    config, _src = load_config(env)
    opts = {"bundle": o["bundle"], "skip_skills": o["skip_skills"], "targets": o["targets"],
            "with_code": o["with_code"], "with_graphify": o["with_graphify"],
            "with_brain": o["with_brain"], "dry": o["dry_run"], "yes": o["yes"]}
    report = onboard(env, config, pos[0], opts)
    if o["json"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(f"Онбординг project:{report['project']} "
          f"({'создан' if report['created'] else 'обновлён'}):")
    for s in report["steps"]:
        mark = {"ok": "✓", "skipped": "○", "failed": "✗"}.get(s["status"], "·")
        print(f"  {mark} {s['name']:<9} {s['detail']}")
