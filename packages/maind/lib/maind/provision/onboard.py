"""maind onboard <project> — единый онбординг: скиллы (skiller) + подключение к мозгу.

Оркеструет цепочку: зарегистрировать проект → skiller integrate (скиллы+хуки) →
maind deploy (память+граф) → seed графа. Каждый шаг standalone-safe: нет соседа — шаг
пропускается с предупреждением, онбординг продолжается. integrate идёт ДО deploy/seed,
чтобы к моменту seed уже существовал skills-lock.json."""
import json
import os
import sys
from pathlib import Path

from ..common import (detect_project_type, die, docs_visibility_for, parse_args,
                     sanitize)
from ..config import load_config
from .deploy import deploy_project, mark_deployed
from .orchestrate import run_capability
from ..projects import get as get_project
from ..projects import write_config


def _infer_type(path):
    """Тип проекта по маркерам — единый детектор core (path уже существует:
    _ensure_project проверил is_dir перед вызовом)."""
    return detect_project_type(path)


def _register_namespaces(config, namespaces):
    """Наполняет реестр `config["namespaces"]` (dict имя→метаданные) записями по умолчанию
    для тех ns, которых там ещё нет — setdefault, чтобы не затирать уже заданные метаданные
    при повторном онбординге (идемпотентно). Реестр — TOP_KEYS['namespaces']=dict, НЕ list;
    projects[i].namespaces — отдельное поле (list строк), сюда не относится."""
    registry = config.get("namespaces")
    if not isinstance(registry, dict):
        registry = {}
        config["namespaces"] = registry
    changed = False
    for ns in namespaces or []:
        if ns not in registry:
            registry.setdefault(ns, {"name": ns})
            changed = True
    return changed


def _ensure_project(env, config, project_or_path, namespaces=None, dry=False):
    """(config, project, created). Новый путь → синтез записи (+ write_config, если не dry).
    namespaces по умолчанию — общий `axioma` + свой `<id>` (несколько на проект).
    Заодно регистрирует эти namespaces в общем реестре `config["namespaces"]`, если их там
    ещё нет (dict-реестр, setdefault — идемпотентно, метаданные не перетираются)."""
    proj = get_project(config, project_or_path)
    if proj is None:
        # get_project матчит ТОЛЬКО по id — `maind onboard <тот же путь>` повторно (не по
        # id, а по абсолютному пути) иначе штампует дубль-запись с тем же id каждый раз
        # (инцидент: loqum x3 в config.json). Доп. матч по local_path (нормализованному),
        # если аргумент похож на реальный каталог.
        from .workspace import norm_path
        cand = norm_path(project_or_path)
        if os.path.isdir(cand):
            for p in config.get("projects") or []:
                lp = p.get("local_path")
                if lp and norm_path(lp) == cand:
                    proj = p
                    break
    if proj is not None:
        return config, proj, False
    path = Path(os.path.expanduser(project_or_path))
    if not path.is_dir():
        die(f"проект не найден: '{project_or_path}' — ни id в config.json, ни каталог")
    pid = sanitize(path.name)
    ptype = _infer_type(path)
    vis = docs_visibility_for(ptype)            # package→public, product→private
    proj_namespaces = list(namespaces) if namespaces else ["axioma", pid]
    proj = {"id": pid, "name": path.name, "local_path": str(path), "repo": None,
            "type": ptype, "enabled": True,
            "memory_scope": f"project:{pid}",
            "namespaces": proj_namespaces,
            "docs_folders": [{"id": "docs", "vault": "docs", "repo": "docs",
                              "visibility": vis}],
            "agents": [], "skills": [], "tags": [], "status": "active", "dependencies": []}
    config["projects"] = list(config.get("projects") or []) + [proj]
    _register_namespaces(config, proj_namespaces)
    if not dry:
        write_config(env, config)
    return config, proj, True


def _wire_memory(env, config, proj, namespaces=None, mechanism="maind", dry=False):
    """Проводка памяти проекта по выбранному механизму (гибко, дефолт `maind`):
    - **maind** (рекомендуется): namespaces (`axioma` + свой) + `.claude/memory.env.ini`
      MODE=maind + SessionStart-инжект дайджеста + выключение нативной авто-памяти
      (`autoMemoryEnabled:false`). Демон — единый источник памяти и контекста.
    - **native**: вернуть нативную авто-память Claude Code (revert хука), MODE=off.
    - **off**: память выключена (MODE=off, native не трогаем).
    Идемпотентно; доводит и уже подключённый проект."""
    from ..health import apply_memory_hook, revert_memory_hook
    changed = False
    if mechanism == "maind":
        if namespaces and proj.get("namespaces") != list(namespaces):
            proj["namespaces"] = list(namespaces)
            changed = True
        elif not proj.get("namespaces"):
            proj["namespaces"] = ["axioma", proj["id"]]
            changed = True
        if _register_namespaces(config, proj["namespaces"]):
            changed = True
        if changed and not dry:
            write_config(env, config)
    wrote = False
    lp = proj.get("local_path")
    mode = {"maind": "maind", "native": "off", "off": "off"}.get(mechanism, "maind")
    if lp and not dry:
        cdir = Path(os.path.expanduser(lp)) / ".claude"
        f = cdir / "memory.env.ini"
        cur = f.read_text(encoding="utf-8") if f.is_file() else ""
        if f"MODE={mode}" not in cur:
            cdir.mkdir(parents=True, exist_ok=True)
            f.write_text(f"# Память проекта — механизм '{mechanism}'.\n"
                         f"# maind = демон + изоляция по scope; native = авто-память Claude Code.\n"
                         f"MODE={mode}\n", encoding="utf-8")
            wrote = True
    # maind → ставим digest-хук + выключаем native; иначе — revert на нативную память.
    if mechanism == "maind":
        hook = apply_memory_hook(env, config, proj, "auto", dry)
    else:
        hook = revert_memory_hook(env, config, proj, dry)
    return {"mechanism": mechanism, "namespaces": proj.get("namespaces"),
            "memory_env_written": wrote, "changed": changed, "memory_hook": hook.get("status")}


def onboard(env, config, project_or_path, opts):
    dry = bool(opts.get("dry"))
    steps = []
    config, proj, created = _ensure_project(env, config, project_or_path,
                                            namespaces=opts.get("namespaces"), dry=dry)
    steps.append({"name": "register", "status": "ok",
                  "detail": f"{'создан' if created else 'найден'} project:{proj['id']}"})

    # 0. память: выбранный механизм (дефолт maind = демон + изоляция + native off + digest-инжект).
    mw = _wire_memory(env, config, proj, namespaces=opts.get("namespaces"),
                      mechanism=opts.get("memory") or "maind", dry=dry)
    steps.append({"name": "memwire", "status": "ok",
                  "detail": f"механизм={mw['mechanism']} ns=[{','.join(mw['namespaces'] or [])}] "
                            f"hook={mw.get('memory_hook')}"})

    # 1. skiller integrate — скиллы + окружение (integrate делегирует permissions/MCP/
    # хуки пакету harness). standalone-safe. При --skip-skills окружение всё равно
    # настраиваем напрямую через harness (env:apply), т.к. integrate не вызывался.
    if opts.get("skip_skills"):
        steps.append({"name": "skills", "status": "skipped", "detail": "--skip-skills"})
        try:
            rc = run_capability(env, config, proj["id"], "env:apply", dry=dry)
            steps.append({"name": "env", "status": "ok" if rc == 0 else "failed",
                          "detail": f"harness permissions rc={rc}"})
        except SystemExit:
            steps.append({"name": "env", "status": "skipped",
                          "detail": "harness недоступен — пропуск"})
    else:
        extra = ["--bundle", opts.get("bundle") or "recommended"]
        # тип проекта (== имя профиля skiller) → явный --profile, чтобы выбор
        # скиллов/пресетов/mcp шёл по профилю типа, а не только по дефолтам бандла.
        # standalone/unknown НЕ передаём явно: пусть skiller сам уйдёт в autodetect-fallback
        # (минимальный набор + warn), а не «поставит всё» по standalone=["*"].
        ptype = proj.get("type")
        if ptype and ptype not in ("unknown", "standalone"):
            extra += ["--profile", ptype]
        # Канал публикации скиллов (только скиллы; память/граф — отдельные плоскости):
        # connect=плагины (не в репо) · vendor=физ.копии в .claude/skills (в репо, для
        # внешних разработчиков без доступа к реестру swissknifeman).
        if opts.get("skills_channel"):
            extra += ["--skills-channel", opts["skills_channel"]]
        if opts.get("yes"):
            extra.append("--yes")
        try:
            rc = run_capability(env, config, proj["id"], "skm:integrate", extra, dry=dry)
            steps.append({"name": "skills", "status": "ok" if rc == 0 else "failed",
                          "detail": f"skiller integrate rc={rc}"})
        except SystemExit:
            steps.append({"name": "skills", "status": "skipped",
                          "detail": "skiller недоступен — пропуск"})

    # 1b. PAO (php/laravel-проект, PHP≥8.3) — токен-экономия вывода PHP-инструментов;
    # инвариант онбординга (SKM-AUDIT-004 P6): доставка скилла ≠ установка зависимости.
    lp = proj.get("local_path")
    if lp:
        from .. import pao
        pstep = pao.apply_pao(proj, Path(os.path.expanduser(lp)),
                              interactive=sys.stdin.isatty() and not opts.get("yes"), dry=dry)
        steps.append(pstep)

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
    from .. import codegraph
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
    from ..federation import graph_disabled
    if dry:
        steps.append({"name": "graph", "status": "skipped", "detail": "--dry-run"})
    elif graph_disabled(config):
        steps.append({"name": "graph", "status": "skipped", "detail": "граф отключён"})
    else:
        from ..derive import derive_project_graph
        from ..federation import Federation, rebuild_index
        d = derive_project_graph(env, config, proj)
        rebuild_index(env, config)
        gstats = Federation(env, config).stats()
        steps.append({"name": "graph", "status": "ok",
                      "detail": f"derive {proj['id']}: {d['nodes']} узлов, "
                                f"{d['edges']} рёбер (code {d['by_via']['code']}, "
                                f"doc {d['by_via']['doc']})"})

    # 3b. seed-память: базовый факт о связях (видимость «память общая»)
    if not dry:
        from ..seed import seed_memory
        ms = seed_memory(env, config, proj)
        steps.append({"name": "memory", "status": "ok" if ms["status"] == "ok" else "skipped",
                      "detail": ms.get("detail", ms["status"])})

    # 3c. ecosystem-skill: управляемый скилл с инструкцией про MCP-инструменты и связи
    from .skilldoc import apply_ecosystem_skill, apply_setup_skill
    try:
        sk = apply_ecosystem_skill(env, config, proj, "auto", dry)
        steps.append({"name": "skill",
                      "status": "ok" if sk["status"] in ("ok", "dry") else "skipped",
                      "detail": f"ecosystem-mcp ({sk.get('detail', sk['status'])})"})
    except OSError as e:
        steps.append({"name": "skill", "status": "skipped", "detail": f"шаблон недоступен: {e}"})

    # 3c-bis. setup-skill: дерево решений тулинга (доезжает до внешних репо — governance B)
    try:
        ss = apply_setup_skill(env, config, proj, "auto", dry)
        steps.append({"name": "setup-skill",
                      "status": "ok" if ss["status"] in ("ok", "dry") else "skipped",
                      "detail": f"ecosystem-setup ({ss.get('detail', ss['status'])})"})
    except OSError as e:
        steps.append({"name": "setup-skill", "status": "skipped",
                      "detail": f"шаблон недоступен: {e}"})

    # 3d. agent-pack профиля проекта — детерминированная доставка субагентов через harness
    # (без агента в цикле). Пак из project.agent_pack или profile.agent_pack по type.
    from .sync import _profile_answers, _resolve_agent_pack
    packs = _resolve_agent_pack(config, proj)
    if packs:
        answers = _profile_answers(config, proj)
        for pack in packs:
            try:
                rc = run_capability(env, config, proj["id"], "env:agent-pack",
                                    ["--pack", pack] + answers, dry=dry)
                steps.append({"name": "agent-pack",
                              "status": "ok" if rc == 0 else "skipped",
                              "detail": f"pack={pack} rc={rc}"})
            except SystemExit:
                steps.append({"name": "agent-pack", "status": "skipped",
                              "detail": f"pack={pack}: harness недоступен"})
    else:
        steps.append({"name": "agent-pack", "status": "skipped",
                      "detail": "профиль без agent_pack"})

    # 4. опционально brain
    if opts.get("with_brain"):
        try:
            run_capability(env, config, proj["id"], "brain:status", dry=dry)
            steps.append({"name": "brain", "status": "ok", "detail": "brain status"})
        except SystemExit:
            steps.append({"name": "brain", "status": "skipped", "detail": "brain недоступен"})

    return {"project": proj["id"], "created": created, "steps": steps,
            "deployed": res is not None, "graph": gstats}


# Шаги, невыполнение которых означает НЕ поставленное окружение/скиллы/MCP — не
# маскируем «зелёным» онбордингом (S9): failed или skipped из-за НЕДОСТУПНОЙ зависимости
# → эскалация в rc≠0 + ATTENTION. Осознанный частичный онбординг снимает --allow-partial.
_CRITICAL_STEPS = {"skills", "env", "deploy"}


def _unmet_steps(report, *, dry):
    """Критичные шаги, не выполненные из-за сбоя/недоступной зависимости (не user-choice).
    В dry-run эскалации нет (это превью). skipped из-за --skip-skills/отключений не считаем."""
    if dry:
        return []
    out = []
    for s in report["steps"]:
        if s["name"] not in _CRITICAL_STEPS:
            continue
        if s["status"] == "failed" or (
                s["status"] == "skipped" and "недоступен" in (s.get("detail") or "")):
            out.append(s)
    return out


def cmd_onboard(env, argv):
    o, pos = parse_args(argv, {"--bundle": "str", "--skip-skills": "bool",
                               "--targets": "str", "--with-code": "bool",
                               "--with-graphify": "bool", "--namespace": "str",
                               "--memory": "str", "--skills-channel": "str",
                               "--with-brain": "bool", "--dry-run": "bool",
                               "--allow-partial": "bool",
                               "--yes": "bool", "--json": "bool"}, max_pos=1)
    if not pos:
        die("использование: maind onboard <project|path> [--memory maind|native|off] "
            "[--skills-channel connect|vendor] [--allow-partial] "
            "[--namespace a,b] [--bundle B --yes --with-code --with-brain --dry-run]")
    config, _src = load_config(env)
    ns = [s.strip() for s in (o["namespace"] or "").split(",") if s.strip()] or None
    # Чек-лист: механизм памяти. Дефолт — maind (демон + изоляция + авто-инжект контекста).
    memory = o["memory"]
    if memory and memory not in ("maind", "native", "off"):
        die(f"--memory: {memory} (допустимо: maind|native|off)")
    if not memory and not o["yes"] and sys.stdin.isatty():
        ans = input("Механизм памяти проекта [maind]/native/off: ").strip().lower()
        memory = ans or "maind"
        if memory not in ("maind", "native", "off"):
            memory = "maind"
    # Чек-лист: канал публикации скиллов. КАСАЕТСЯ ТОЛЬКО СКИЛЛОВ — память/граф/MCP
    # настраиваются как обычно. connect=плагины (не в репо, нужен реестр swissknifeman);
    # vendor=физ.копии в .claude/skills (коммитятся в репо — для проектов, которые
    # отдают сторонним разработчикам без доступа к swissknifeman).
    channel = o["skills_channel"]
    if channel and channel not in ("connect", "vendor"):
        die(f"--skills-channel: {channel} (допустимо: connect|vendor)")
    if not channel and not o["yes"] and not o["skip_skills"] and sys.stdin.isatty():
        ans = input("Публикация скиллов [connect]/vendor "
                    "(connect=плагины, не в репо · vendor=физ.копии в репо для "
                    "внешних разработчиков): ").strip().lower()
        channel = ans if ans in ("connect", "vendor") else "connect"
    opts = {"bundle": o["bundle"], "skip_skills": o["skip_skills"], "targets": o["targets"],
            "with_code": o["with_code"], "with_graphify": o["with_graphify"],
            "namespaces": ns, "memory": memory or "maind", "skills_channel": channel,
            "with_brain": o["with_brain"], "dry": o["dry_run"], "yes": o["yes"]}
    report = onboard(env, config, pos[0], opts)
    unmet = _unmet_steps(report, dry=opts["dry"])
    report["attention"] = [s["name"] for s in unmet]
    if o["json"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Онбординг project:{report['project']} "
              f"({'создан' if report['created'] else 'обновлён'}):")
        for s in report["steps"]:
            mark = {"ok": "✓", "skipped": "○", "failed": "✗"}.get(s["status"], "·")
            print(f"  {mark} {s['name']:<9} {s['detail']}")
        if unmet:
            names = ", ".join(f"{s['name']} ({s['detail']})" for s in unmet)
            print(f"\n⚠ ATTENTION: критичные шаги не выполнены: {names}")
    if unmet and not o["allow_partial"]:
        die("онбординг НЕ полон (окружение/скиллы/MCP не поставлены): "
            f"{', '.join(report['attention'])}. Поставь harness/skiller и повтори, "
            "либо запусти с --allow-partial.")
