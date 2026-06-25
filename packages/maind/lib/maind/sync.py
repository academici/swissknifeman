"""maind sync — единый провижининг: проанализировать config.json и раскатать управляемые
артефакты на все подключённые проекты ОДНОЙ командой.

Каждый артефакт — провиженер с `run(env, config, projects, mode, dry) → [result]`. Реестр
PROVISIONERS + порядок ORDER; `--only` сужает набор. Режим (mode) задаёт «метод синка по
области»: install — первичная установка (создать, если нет), update — обновить уже
существующее (drift по хэшу), auto — и то, и другое (нет→install, устарело→update, свежо→skip).

Фан-аут по проектам и резолв пути/scope вынесены сюда (DRY): deploy/derive/seed/health —
провиженеры поверх одного контекста, а не дубль цикла в каждом модуле."""
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .common import die, parse_args, safe_load_json
from .config import load_config
from .namespaces import in_namespace
from .projects import get as get_project
from .projects import listing

MODES = ("install", "update", "auto")


# ── контекст проекта (единый резолв пути/scope) ──────────────────────────────
@dataclass
class ProjectContext:
    env: object
    config: dict
    project: dict

    @property
    def id(self):
        return self.project["id"]

    @property
    def path(self):
        local = self.project.get("local_path")
        return Path(os.path.expanduser(local)) if local else None

    @property
    def exists(self):
        p = self.path
        return p is not None and p.is_dir()

    @property
    def scope(self):
        return self.project.get("memory_scope") or f"project:{self.id}"


def select_projects(env, config, opts):
    """Фан-аут: --project <id> | --namespace <ns> | --all (enabled). Единственный
    источник выборки проектов."""
    if opts.get("project"):
        proj = get_project(config, opts["project"])
        if proj is None:
            die(f"проект не найден в config.json: {opts['project']}")
        return [proj]
    if opts.get("namespace"):
        projs = [p for p in listing(env, config)
                 if p.get("enabled", True) and in_namespace(p, opts["namespace"])]
        if not projs:
            die(f"в namespace '{opts['namespace']}' нет enabled-проектов")
        return projs
    if opts.get("all"):
        return [p for p in listing(env, config) if p.get("enabled", True)]
    die("укажите --project <id>, --namespace <ns> или --all")


def contexts(env, config, projects):
    return [ProjectContext(env, config, p) for p in projects]


# ── провиженеры ──────────────────────────────────────────────────────────────
def _mcp_run(env, config, projects, mode, dry):
    """MCP-серверы хаба (agent-memory + maind [+ код-граф/Serena]) в конфиги проектов."""
    from .deploy import deploy_project, mark_deployed
    from .projects import write_config
    results, applied = [], False
    for p in projects:
        res = deploy_project(env, config, p, dry=dry)  # with_code=None → из политики/полей проекта
        if res is None:
            results.append({"provisioner": "mcp", "id": p["id"], "status": "skip",
                            "detail": "нет/нет пути проекта"})
            continue
        changed = any(w["changed"] for w in res["written"])
        if not dry:
            mark_deployed(config, p["id"], res)
            applied = True
        results.append({"provisioner": "mcp", "id": p["id"],
                        "status": "ok", "changed": changed,
                        "detail": ", ".join(res["targets"])})
    if applied:
        write_config(env, config)
    return results


def _codegraph_run(env, config, projects, mode, dry):
    """Дефолтный .serena/project.yml в проекты с включённым код-графом (движок Serena)."""
    from .codegraph import apply_serena_config
    return [apply_serena_config(env, config, p, mode, dry) for p in projects]


def _graph_run(env, config, projects, mode, dry):
    """Derive графа проектов из источников (composer/Brain/override) + пересборка индекса.
    changed — честно по содержимому стора (сериализация детерминирована), чтобы
    --mode update не сообщал об изменении там, где граф фактически не поменялся."""
    from .derive import build_provider_index, derive_project_graph
    from .federation import rebuild_index, store_path
    results = []
    if dry:
        return [{"provisioner": "graph", "id": p["id"], "status": "dry"} for p in projects]
    providers = build_provider_index(env, config)
    for p in projects:
        sp = Path(store_path(env, config, p))
        before = sp.read_bytes() if sp.exists() else None
        d = derive_project_graph(env, config, p, providers)
        after = sp.read_bytes() if sp.exists() else None
        results.append({"provisioner": "graph", "id": p["id"], "status": "ok",
                        "changed": before != after,
                        "detail": f"{d['nodes']}n/{d['edges']}e "
                                  f"(code {d['by_via']['code']}, doc {d['by_via']['doc']})"})
    rebuild_index(env, config)
    return results


def _memory_run(env, config, projects, mode, dry):
    """Seed-память: базовый факт о связях проекта в project:<id> + cross-ref в global."""
    from .seed import seed_memory
    return [seed_memory(env, config, p, dry=dry) for p in projects]


def _health_hook_run(env, config, projects, mode, dry):
    """SessionStart-хук связи с хабом (НЕ блокирует) в .claude/settings.json проектов."""
    from .health import apply_health_hook
    return [apply_health_hook(env, config, p, mode, dry) for p in projects]


def _memory_hook_run(env, config, projects, mode, dry):
    """SessionStart-инжект ДАЙДЖЕСТА памяти + выключение нативной авто-памяти — по интенту
    проекта из .claude/memory.env.ini: MODE=maind → ставим (apply_memory_hook), MODE=off →
    откатываем на native (revert_memory_hook), нет конфига → не трогаем. Так `maind sync`
    раскатывает авто-загрузку памяти на уже подключённые проекты, не гоняя полный onboard."""
    from .health import (apply_memory_hook, hook_memory_mode, revert_memory_hook)
    results = []
    for p in projects:
        hmode = hook_memory_mode(p)
        if hmode == "maind":
            results.append(apply_memory_hook(env, config, p, mode, dry))
        elif hmode is not None:                       # off/native — вернуть нативную память
            results.append(revert_memory_hook(env, config, p, dry))
        else:                                         # память проекта не сконфигурирована
            results.append({"provisioner": "memory-hook", "id": p["id"], "status": "skip",
                            "changed": False, "state": "absent",
                            "detail": "нет MODE в .claude/memory.env.ini — пропуск"})
    return results


def _health_doc_run(env, config, projects, mode, dry):
    """Управляемый блок «ПРИОРИТЕТ №1 — связь с mAInd» в CLAUDE.md проектов."""
    from .health import apply_health_doc
    return [apply_health_doc(env, config, p, mode, dry) for p in projects]


def _feature_log_hook_run(env, config, projects, mode, dry):
    """SessionEnd-хук фиксации коммитов в общую память (если code_graph.feature_log_hook)."""
    from .codegraph import settings
    if not settings(config).get("feature_log_hook", True):
        return [{"provisioner": "feature-log-hook", "id": p["id"], "status": "skip",
                 "changed": False, "state": "disabled", "detail": "выключен в конфиге"}
                for p in projects]
    from .health import apply_feature_log_hook
    return [apply_feature_log_hook(env, config, p, mode, dry) for p in projects]


def _ecosystem_skill_run(env, config, projects, mode, dry):
    """Управляемый скилл ecosystem-mcp (инструкция про MCP-инструменты и связи) в проекты."""
    from .skilldoc import apply_ecosystem_skill
    return [apply_ecosystem_skill(env, config, p, mode, dry) for p in projects]


def _skiller_profiles_dir(config):
    """Каталог профилей skiller (<repo>/packages/skiller/profiles) или None.
    Резолв корня репо — как у orchestrate._sibling_bin (проект 'swissknifeman')."""
    from .orchestrate import SIBLINGS
    spec = SIBLINGS["swissknifeman"]
    proj = get_project(config, spec["project_id"])
    root = proj.get(spec["path_key"]) if proj else None
    if not root:
        return None
    d = Path(os.path.expanduser(root)) / "packages" / "skiller" / "profiles"
    return d if d.is_dir() else None


def _profile_for(config, project):
    """Профиль skiller по project.type (dict) или {}."""
    pdir, ptype = _skiller_profiles_dir(config), project.get("type")
    if not pdir or not ptype:
        return {}
    return safe_load_json(pdir / f"{ptype}.json", default={}) or {}


def _resolve_agent_pack(config, project):
    """Паки проекта: project.agent_pack (str|list) > profile.agent_pack по project.type,
    ПЛЮС роль-паки (вариант C): project.roles → config.role_packs[role] — кросс-стек паки
    персон поверх стекового пака профиля. [] — ничего не определилось (шаг пропустится)."""
    explicit = project.get("agent_pack")
    if isinstance(explicit, str):
        packs = [explicit]
    elif isinstance(explicit, list):
        packs = list(explicit)
    else:
        pack = _profile_for(config, project).get("agent_pack")
        packs = [pack] if isinstance(pack, str) else (list(pack) if isinstance(pack, list) else [])
    # роль-паки: project.roles (выбранные роли) → пак из config.role_packs, аддитивно
    role_map = config.get("role_packs") or {}
    for role in (project.get("roles") or []):
        rp = role_map.get(role)
        if rp and rp not in packs:
            packs.append(rp)
    return packs


def _profile_answers(config, project):
    """Доп. --answer для рендера из профиля: model_tiers (role → MODEL_<ROLE>=tier).
    Так профиль типа проекта пре-заполняет модельные тиры агентов пака."""
    out = []
    for role, tier in (_profile_for(config, project).get("model_tiers") or {}).items():
        out += ["--answer", f"MODEL_{role.upper().replace('-', '_')}={tier}"]
    return out


def _agent_pack_run(env, config, projects, mode, dry):
    """Детерминированно раскатать agent-pack(и) профиля проекта в .claude/ через harness
    (без агента в цикле). install — только если ещё не стоит; update — версионный апгрейд;
    auto — render --auto (install + идемпотентный ре-ролл). Нет пака/пути/harness → skip."""
    from .orchestrate import run_capability
    results = []
    for p in projects:
        packs = _resolve_agent_pack(config, p)
        if not packs or not p.get("local_path"):
            results.append({"provisioner": "agent-pack", "id": p["id"], "status": "skip",
                            "changed": False, "detail": "нет профиля/agent_pack или пути"})
            continue
        answers = _profile_answers(config, p)
        for pack in packs:
            cap = "env:agent-pack-upgrade" if mode == "update" else "env:agent-pack"
            extra = (["--pack", pack] + answers
                     + (["--install-only"] if mode == "install" else []))
            try:
                rc = run_capability(env, config, p["id"], cap, extra, dry=dry)
                results.append({"provisioner": "agent-pack", "id": p["id"],
                                "status": "ok" if rc == 0 else "skip",
                                "detail": f"pack={pack} rc={rc}"})
            except SystemExit:
                results.append({"provisioner": "agent-pack", "id": p["id"],
                                "status": "skip", "changed": False,
                                "detail": f"pack={pack}: harness недоступен"})
    return results


# Реестр провиженеров и порядок применения (ORDER задаёт последовательность).
PROVISIONERS = {
    "mcp": _mcp_run,
    "code-graph": _codegraph_run,
    "graph": _graph_run,
    "memory": _memory_run,
    "memory-hook": _memory_hook_run,
    "health-hook": _health_hook_run,
    "health-doc": _health_doc_run,
    "feature-log-hook": _feature_log_hook_run,
    "ecosystem-skill": _ecosystem_skill_run,
    "agent-pack": _agent_pack_run,
}
ORDER = ["mcp", "code-graph", "graph", "memory", "memory-hook", "health-hook",
         "health-doc", "feature-log-hook", "ecosystem-skill", "agent-pack"]


def provisioner_names(only=None):
    """Имена провиженеров в порядке ORDER, ограниченные --only (csv) и реестром."""
    if only:
        want = [x.strip() for x in only.split(",") if x.strip()]
        for x in want:
            if x not in PROVISIONERS:
                die(f"неизвестный провиженер: {x} (есть: {', '.join(sorted(PROVISIONERS))})")
        return [n for n in ORDER if n in want]
    return [n for n in ORDER if n in PROVISIONERS]


def run_sync(env, config, projects, *, only=None, mode="auto", dry=False):
    """Применить выбранные провиженеры к проектам. Возвращает плоский список результатов."""
    results = []
    for name in provisioner_names(only):
        results.extend(PROVISIONERS[name](env, config, projects, mode, dry))
    return results


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_sync(env, argv):
    opts, _ = parse_args(argv, {"--project": "str", "--namespace": "str", "--all": "bool",
                                "--only": "str", "--mode": "str", "--dry-run": "bool",
                                "--json": "bool"})
    if opts["help"]:
        print("maind sync [--project ID | --namespace NS | --all] [--only mcp,code-graph,"
              "graph,memory,memory-hook,health-hook,health-doc,feature-log-hook,"
              "ecosystem-skill,agent-pack] [--mode install|update|auto] [--dry-run] [--json]")
        return
    mode = opts["mode"] or "auto"
    if mode not in MODES:
        die(f"--mode: {', '.join(MODES)} (получено: {mode})")
    config, _src = load_config(env)
    projects = select_projects(env, config, opts)
    results = run_sync(env, config, projects, only=opts["only"], mode=mode,
                       dry=opts["dry_run"])
    if opts["json"]:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    tag = "[dry-run] " if opts["dry_run"] else ""
    print(f"{tag}sync (mode={mode}, проектов {len(projects)}, "
          f"провиженеры: {', '.join(provisioner_names(opts['only']))})")
    for r in results:
        mark = {"ok": "✓", "skip": "○", "dry": "·"}.get(r["status"], "·")
        if r["status"] == "dry":
            note = f" (план: {r.get('state', 'apply')})"
        elif r["status"] == "ok" and not r.get("changed", True):
            note = " (без изменений)"
        else:
            note = ""
        print(f"  {mark} {r['provisioner']:<11} {r['id']:<18} {r.get('detail', '')}{note}")
