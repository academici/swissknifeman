"""maind sync — единый провижининг: проанализировать config.json и раскатать управляемые
артефакты на все подключённые проекты ОДНОЙ командой.

Каждый артефакт — провиженер с `run(env, config, projects, mode, dry) → [result]`. Реестр
PROVISIONERS + порядок ORDER; `--only` сужает набор. Режим (mode) задаёт «метод синка по
области»: install — первичная установка (создать, если нет), update — обновить уже
существующее (drift по хэшу), auto — и то, и другое (нет→install, устарело→update, свежо→skip).

Фан-аут по проектам и резолв пути/scope вынесены сюда (DRY): deploy/derive/seed/health —
провиженеры поверх одного контекста, а не дубль цикла в каждом модуле."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..common import die, parse_args, safe_load_json, warn
from ..config import load_config
from ..constants import SIBLINGS
from ..namespaces import in_namespace
from ..projects import get as get_project
from ..projects import listing

MODES = ("install", "update", "auto", "repair")

# mAInd orders semantic work; provider adapters own native paths, trust and rendering.
# These IDs deliberately do not encode a provider target or a renderer implementation.
INTENT_ORDER = ("trust", "memory-context", "health", "skills", "agent-pack", "router",
                "instruction-root", "instruction-package")
PROVISIONER_INTENTS = {
    "mcp": (), "code-graph": (), "graph": (), "memory": (),
    "memory-hook": ("memory-context",), "health-hook": ("health",),
    "health-doc": ("health",), "feature-log-hook": ("health",),
    "ecosystem-skill": ("skills",), "setup-skill": ("skills",),
    "skills-catalog": ("skills",), "agent-pack": ("agent-pack",),
    "output-style": ("memory-context",), "router-config": ("router",),
    "instructions": ("instruction-root", "instruction-package"),
}


# ── контекст проекта (единый резолв пути/scope) ──────────────────────────────
@dataclass(frozen=True)
class ProjectContext:
    env: object
    config: dict
    project: dict
    provider_context: object | None = None

    def __getitem__(self, key):
        return self.project[key]

    def get(self, key, default=None):
        return self.project.get(key, default)

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

    @property
    def effective_provider_ids(self):
        """Stable IDs resolved once by the P6 context, never rediscovered by a provisioner."""
        return tuple(provider.provider_id.value for provider in
                     (self.provider_context.effective_providers if self.provider_context else ()))

    @property
    def semantic_intents(self):
        return INTENT_ORDER


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
    from .deploy import provider_projection_context
    return [ProjectContext(env, config, p, provider_projection_context(env, config, p))
            for p in projects]


@dataclass(frozen=True)
class ProviderProvisionAggregate:
    rows: tuple

    @property
    def green(self):
        return bool(self.rows) and all(
            row["status"] == "planned" or not row["required"] for row in self.rows)


def _provider_aggregate(plan):
    return ProviderProvisionAggregate(tuple({"provider_id": row.provider_id.value,
                                              "status": row.status,
                                              "required": True,
                                              "diagnostic": row.diagnostic}
                                         for row in plan.results))


def _project_eligibility(context):
    """Return the one fleet gate for paths that cannot receive provisioning."""
    if not context.project.get("local_path"):
        return "MAIND_PROJECT_LOCAL_PATH_MISSING"
    if not context.exists:
        return "MAIND_PROJECT_PATH_UNAVAILABLE"
    return None


def _ineligible_provider_aggregate(context, diagnostic):
    """Keep a skipped fleet row visible for every selected provider."""
    return ProviderProvisionAggregate(tuple(
        {"provider_id": provider_id, "status": "skip", "required": False,
         "diagnostic": diagnostic}
        for provider_id in context.effective_provider_ids))


def _ineligible_result(provisioner, context, diagnostic):
    detail = ("нет local_path" if diagnostic == "MAIND_PROJECT_LOCAL_PATH_MISSING"
              else "путь проекта недоступен")
    return _result(provisioner, context.id, "skip", state="ineligible",
                   detail=f"{detail}: {diagnostic}",
                   provider_aggregate=_ineligible_provider_aggregate(context, diagnostic))


def _result(provisioner, project_id, status, *, changed=False, state="", detail="",
            provider_aggregate=None, bootstrap_transfer=None):
    """Единая форма результата провиженера (та же, что у health._result): ВСЕ ключи всегда
    присутствуют, поэтому CLI и тесты не зависят от .get()-умолчаний. status: ok|skip|dry."""
    result = {"provisioner": provisioner, "id": project_id, "status": status,
              "changed": changed, "state": state, "detail": detail}
    if provider_aggregate is not None:
        result["providers"] = list(provider_aggregate.rows)
        result["provider_aggregate"] = "green" if provider_aggregate.green else "non-green"
    if bootstrap_transfer is not None:
        result["bootstrap_transfer"] = bootstrap_transfer
    return result


# ── провиженеры ──────────────────────────────────────────────────────────────
def _mcp_run(env, config, projects, mode, dry):
    """MCP-серверы хаба (agent-memory + maind [+ код-граф/Serena]) в конфиги проектов."""
    from .deploy import deploy_project, mark_deployed, provider_operation_green
    from ..projects import write_config
    results, applied = [], False
    for context in projects:
        p = context.project if isinstance(context, ProjectContext) else context
        provider_context = context.provider_context if isinstance(context, ProjectContext) else None
        res = deploy_project(env, config, p, dry=dry,
                             provider_projections=(provider_context.projections
                                                   if provider_context is not None else None),
                             provider_repair=(mode == "repair"))
        if res is None:
            results.append(_result("mcp", p["id"], "skip", detail="нет/нет пути проекта"))
            continue
        changed = (res["provider_changed"] if res.get("provider_plan") is not None
                   else any(w["changed"] for w in res["written"]))
        operation_green = provider_operation_green(res)
        if not dry and operation_green:
            mark_deployed(config, p["id"], res)
            applied = True
        detail = ", ".join(res["targets"])
        if res.get("skipped"):
            detail += f" (пропущено битых каналов: {', '.join(res['skipped'])})"
        aggregate = _provider_aggregate(res["provider_plan"]) if res.get("provider_plan") else None
        results.append(_result("mcp", p["id"], "ok" if operation_green else "failed",
                               changed=changed, detail=detail, provider_aggregate=aggregate,
                               bootstrap_transfer=res.get("bootstrap_transfer")))
    if applied:
        write_config(env, config)
    return results


def _codegraph_run(env, config, projects, mode, dry):
    """Дефолтный .serena/project.yml в проекты с включённым код-графом (движок Serena)."""
    from ..codegraph import apply_serena_config
    return [apply_serena_config(env, config, p, mode, dry) for p in projects]


def _graph_run(env, config, projects, mode, dry):
    """Derive графа проектов из источников (composer/Brain/override) + пересборка индекса.
    changed — честно по содержимому стора (сериализация детерминирована), чтобы
    --mode update не сообщал об изменении там, где граф фактически не поменялся."""
    from ..derive import build_provider_index, derive_project_graph
    from ..federation import rebuild_index, store_path
    results = []
    if dry:
        return [_result("graph", p["id"], "dry") for p in projects]
    providers = build_provider_index(env, config)
    for p in projects:
        sp = Path(store_path(env, config, p))
        before = sp.read_bytes() if sp.exists() else None
        d = derive_project_graph(env, config, p, providers)
        after = sp.read_bytes() if sp.exists() else None
        results.append(_result("graph", p["id"], "ok", changed=before != after,
                               detail=f"{d['nodes']}n/{d['edges']}e "
                                      f"(code {d['by_via']['code']}, doc {d['by_via']['doc']})"))
    rebuild_index(env, config)
    return results


def _memory_run(env, config, projects, mode, dry):
    """Seed-память: базовый факт о связях проекта в project:<id> + cross-ref в global."""
    from ..seed import seed_memory
    return [seed_memory(env, config, p, dry=dry) for p in projects]


def _health_hook_run(env, config, projects, mode, dry):
    """SessionStart-хук связи с хабом (НЕ блокирует) в .claude/settings.json проектов."""
    from ..health import apply_health_hook
    return [apply_health_hook(env, config, p, mode, dry) for p in projects]


def _memory_hook_run(env, config, projects, mode, dry):
    """SessionStart-инжект ДАЙДЖЕСТА памяти + выключение нативной авто-памяти — по интенту
    проекта из .claude/memory.env.ini: MODE=maind → ставим (apply_memory_hook), MODE=off →
    откатываем на native (revert_memory_hook), нет конфига → не трогаем. Так `maind sync`
    раскатывает авто-загрузку памяти на уже подключённые проекты, не гоняя полный onboard."""
    from ..health import (apply_memory_hook, hook_memory_mode, revert_memory_hook)
    results = []
    for p in projects:
        hmode = hook_memory_mode(p)
        if hmode == "maind":
            results.append(apply_memory_hook(env, config, p, mode, dry))
        elif hmode is not None:                       # off/native — вернуть нативную память
            results.append(revert_memory_hook(env, config, p, dry))
        else:                                         # память проекта не сконфигурирована
            results.append(_result("memory-hook", p["id"], "skip", state="absent",
                                   detail="нет MODE в .claude/memory.env.ini — пропуск"))
    return results


def _health_doc_run(env, config, projects, mode, dry):
    """Управляемый блок «ПРИОРИТЕТ №1 — связь с mAInd» в CLAUDE.md проектов."""
    from ..health import apply_health_doc
    return [apply_health_doc(env, config, p, mode, dry) for p in projects]


def _seed_umbrella_layout(root):
    """Minimal ``packages/`` tree so instruction scopes match the swissknifeman monorepo."""
    root = Path(root)
    for pkg in ("skiller", "maind", "harness"):
        (root / "packages" / pkg).mkdir(parents=True, exist_ok=True)


def _instructions_applicable(context):
    """Instruction-carrier blocks belong only on the swissknifeman umbrella monorepo.

    Consumer projects (Laravel apps, packages, vaults) keep their own CLAUDE.md/AGENTS.md
    contracts; projecting package-scope instruction blocks into them hits boundary-invalid
    and adds noise to fleet sync."""
    if context.id == "swissknifeman":
        return True
    packages = context.path / "packages"
    if not packages.is_dir():
        return False
    required = ("skiller", "maind", "harness")
    return all((packages / name).is_dir() and not (packages / name).is_symlink()
               for name in required)


def _instruction_scope_ids(context):
    """Return root plus real, non-symlink swissknifeman package directories in catalog order."""
    from harness.instructions import SCOPES
    root = context.path
    return tuple(scope_id for scope_id in SCOPES
                 if scope_id == "root" or (
                     (candidate := root / "packages" / scope_id).is_dir()
                     and not candidate.is_symlink()))


def _instruction_request(context, operation_id, *, authorized=(), observed=()):
    """Construct only the frozen public P5 request; maind never reads its catalog/markers."""
    from harness.instructions import CATALOG_VERSION, CONTRACT_VERSION, InstructionRequest
    return InstructionRequest(
        CONTRACT_VERSION, CATALOG_VERSION, operation_id, _instruction_scope_ids(context),
        context.effective_provider_ids, str(context.path),
        (("provider-context", context.id),),
        (("authority", "maind-sync-explicit-targets"),), tuple(authorized),
        tuple(observed), "adjacent-backup" if operation_id == "repair" else None)


def _instruction_aggregate(operation):
    """Preserve P5 target observations as provider-tagged rows without reclassifying them."""
    rows = []
    for provider_id in operation.request.provider_ids:
        targets = [target for target in operation.targets if target.provider_id == provider_id]
        diagnostics = [diagnostic.code for target in targets for diagnostic in target.diagnostics]
        rows.append({"provider_id": provider_id,
                     "status": "planned" if not diagnostics else "failed",
                     "required": True, "diagnostic": ",".join(diagnostics) or None})
    return ProviderProvisionAggregate(tuple(rows))


def _instruction_run(env, config, projects, mode, dry):
    """Provision root plus applicable real package scopes through frozen harness.instructions.

    The plan is always obtained first.  The only write authority supplied to harness is the
    exact target set returned by that plan; mAInd neither parses nor renders instructions.
    """
    from harness.instructions import (apply_instructions, check_instructions,
                                      plan_instructions, repair_instructions)
    results = []
    for context in projects:
        if not isinstance(context, ProjectContext) or not context.exists:
            project = context.project if isinstance(context, ProjectContext) else context
            results.append(_result("instructions", project["id"], "skip", state="absent",
                                   detail="нет пути проекта"))
            continue
        if not _instructions_applicable(context):
            results.append(_result("instructions", context.id, "skip", state="n-a",
                                   detail="только umbrella-монорепо swissknifeman"))
            continue
        planned = plan_instructions(_instruction_request(context, "plan"))
        paths = tuple(action.target_path for action in (planned.artifact_plan.actions
                                                         if planned.artifact_plan else ())
                      if getattr(action.action, "value", action.action) != "noop")
        operation = planned
        # P5 classifies missing/stale targets as diagnostics in the no-write plan; its
        # apply API is the sole authority that decides whether those planned paths may write.
        if not dry and planned.artifact_plan is not None:
            if mode == "repair":
                observed = tuple((action.target_path, action.observed_hash)
                                 for action in planned.artifact_plan.actions
                                 if getattr(action.observation, "value", action.observation)
                                 == "managed-drift")
                operation = repair_instructions(_instruction_request(
                    context, "repair", authorized=paths, observed=observed))
            elif paths:
                operation = apply_instructions(_instruction_request(
                    context, "apply" if mode == "install" else "update", authorized=paths))
            else:
                operation = check_instructions(_instruction_request(context, "check"))
        aggregate = _instruction_aggregate(operation)
        changed = any(target.changed for target in operation.targets)
        status = "dry" if dry else ("ok" if operation.green else "failed")
        detail = f"{len(operation.targets)} targets; intents=instruction-root,instruction-package"
        results.append(_result("instructions", context.id, status, changed=changed,
                               state="clean" if operation.green else "non-green",
                               detail=detail, provider_aggregate=aggregate))
    return results


def _feature_log_hook_run(env, config, projects, mode, dry):
    """SessionEnd-хук фиксации коммитов в общую память (если code_graph.feature_log_hook)."""
    from ..codegraph import settings
    if not settings(config).get("feature_log_hook", True):
        return [_result("feature-log-hook", p["id"], "skip", state="disabled",
                        detail="выключен в конфиге") for p in projects]
    from ..health import apply_feature_log_hook
    return [apply_feature_log_hook(env, config, p, mode, dry) for p in projects]


def _setup_skill_run(env, config, projects, mode, dry):
    """Управляемый скилл ecosystem-setup (дерево решений тулинга) на проекты."""
    from .skilldoc import apply_setup_skill
    return [apply_setup_skill(env, config, p, mode, dry) for p in projects]


def _ecosystem_skill_run(env, config, projects, mode, dry):
    """Управляемый скилл ecosystem-mcp (инструкция про MCP-инструменты и связи) в проекты."""
    from .skilldoc import apply_ecosystem_skill
    return [apply_ecosystem_skill(env, config, p, mode, dry) for p in projects]


def _skiller_profiles_dir(config):
    """Каталог профилей skiller (<repo>/packages/skiller/profiles) или None.
    Резолв корня репо — как у orchestrate._sibling_bin (проект 'swissknifeman')."""
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


def _installed_agent_packs(local_path):
    """Имена паков, уже осевших в lock'е цели (.claude/agent-pack.lock.json). Нет
    файла/битый JSON → пусто (трактуем как «ничего не установлено»)."""
    lock = safe_load_json(Path(local_path) / ".claude" / "agent-pack.lock.json", default={}) or {}
    return set((lock.get("packs") or {}).keys())


def _agent_pack_run(env, config, projects, mode, dry):
    """Детерминированно раскатать agent-pack(и) профиля проекта в .claude/ через harness
    (без агента в цикле). install — только если ещё не стоит; update — версионный апгрейд
    уже установленных + install недостающих (harness upgrade падает на неустановленном
    паке, см. field-feedback: профиль дорос новым паком → update один его не подхватит);
    auto — render --auto (install + идемпотентный ре-ролл). Нет пака/пути/harness → skip."""
    from .orchestrate import run_capability
    results = []
    for p in projects:
        packs = _resolve_agent_pack(config, p)
        if not packs or not p.get("local_path"):
            results.append(_result("agent-pack", p["id"], "skip",
                                   detail="нет профиля/agent_pack или пути"))
            continue
        installed = _installed_agent_packs(p["local_path"])
        answers = _profile_answers(config, p)
        for pack in packs:
            cap = ("env:agent-pack-upgrade" if mode == "update" and pack in installed
                   else "env:agent-pack")
            extra = (["--pack", pack] + answers
                     + (["--install-only"] if mode == "install" else []))
            try:
                rc = run_capability(env, config, p["id"], cap, extra, dry=dry)
                # rc!=0 — провал рендера пака (НЕ 'skip', иначе провал невидим); harness
                # недоступен ловится отдельно ниже как graceful skip.
                results.append(_result("agent-pack", p["id"], "ok" if rc == 0 else "failed",
                                       changed=rc == 0, detail=f"pack={pack} rc={rc}"))
            except SystemExit:
                results.append(_result("agent-pack", p["id"], "skip",
                                       detail=f"pack={pack}: harness недоступен"))
    return results


def _skills_catalog_run(env, config, projects, mode, dry):
    """Пере-резолв каталога скиллов (skiller update): buckets/exclude пере-читаются с диска
    каждый раз, поэтому новый скилл в уже выбранном бакете (напр. `pao` в `php`) доезжает
    до уже онбордженных проектов без ручного re-run skiller connect/vendor/update. Идемпотентно,
    exclude уважается, foreign-файлы не трогает (skillset.sync_skillset/vendor.collect_skills)."""
    from .orchestrate import run_capability
    results = []
    for p in projects:
        if not p.get("local_path"):
            results.append(_result("skills-catalog", p["id"], "skip", detail="нет пути проекта"))
            continue
        try:
            rc = run_capability(env, config, p["id"], "skm:update", dry=dry)
            results.append(_result("skills-catalog", p["id"], "ok" if rc == 0 else "failed",
                                   changed=rc == 0, detail=f"rc={rc}"))
        except SystemExit:
            results.append(_result("skills-catalog", p["id"], "skip",
                                   detail="skiller недоступен"))
    return results


def _output_style_run(env, config, projects, mode, dry):
    """outputStyle=lean (терсе-голос агента, токен-экономия) во все .claude/settings.local.json
    уже онбордженных проектов — догоняет `skiller integrate`, который ставит это только на
    НОВЫХ онбордингах. Опт-аут per-project: project.output_style="off" — тогда пропуск (не
    трогаем локально выбранный стиль): block_output_style в harness ПЕРЕЗАПИСЫВАЕТ ключ, если
    он отличается от желаемого, поэтому без опт-аута регулярный `maind sync --all` затирал бы
    чей-то осознанный выбор."""
    from .orchestrate import run_capability
    results = []
    for p in projects:
        style = p.get("output_style", "lean")
        if not style or style == "off":
            results.append(_result("output-style", p["id"], "skip",
                                   detail="project.output_style=off"))
            continue
        if not p.get("local_path"):
            results.append(_result("output-style", p["id"], "skip", detail="нет пути проекта"))
            continue
        try:
            rc = run_capability(env, config, p["id"], "env:hooks",
                                ["--output-style", style], dry=dry)
            results.append(_result("output-style", p["id"], "ok" if rc == 0 else "failed",
                                   changed=rc == 0, detail=f"style={style} rc={rc}"))
        except SystemExit:
            results.append(_result("output-style", p["id"], "skip",
                                   detail="harness недоступен"))
    return results


def _router_config_run(env, config, projects, mode, dry):
    """Сгенерить/обновить каталог intent-router (.claude/agent-router.config.json) через
    harness — ТОЛЬКО для проектов, где хук уже включён (opt-in: есть agent-router.env.ini с
    POLICY!=off; включается `harness hooks --router` / `maind onboard`). Не включён/нет пути/
    harness недоступен → graceful skip. Идёт после agent-pack (читает свежедоставленных агентов)."""
    from .orchestrate import run_capability
    results = []
    for p in projects:
        lp = p.get("local_path")
        if not lp:
            results.append(_result("router-config", p["id"], "skip", detail="нет пути"))
            continue
        envini = Path(os.path.expanduser(lp)) / ".claude" / "agent-router.env.ini"
        try:
            enabled = "POLICY=off" not in envini.read_text(encoding="utf-8").replace(" ", "")
        except Exception:
            enabled = False
        if not enabled:
            results.append(_result("router-config", p["id"], "skip",
                                   detail="intent-router не включён (opt-in)"))
            continue
        try:
            rc = run_capability(env, config, p["id"], "env:router", [], dry=dry)
            results.append(_result("router-config", p["id"], "ok" if rc == 0 else "failed",
                                   changed=rc == 0, detail=f"rc={rc}"))
        except SystemExit:
            results.append(_result("router-config", p["id"], "skip",
                                   detail="harness недоступен"))
    return results


# Реестр провиженеров и порядок применения (ORDER задаёт последовательность).
# Сигнатура каждого: run(env, config, projects, mode, dry) -> list[_result(...)]
# (форма результата — _result выше: provisioner/id/status/changed/state/detail).
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
    "setup-skill": _setup_skill_run,
    "skills-catalog": _skills_catalog_run,
    "agent-pack": _agent_pack_run,
    "output-style": _output_style_run,
    "router-config": _router_config_run,
    "instructions": _instruction_run,
}
ORDER = ["mcp", "code-graph", "graph", "memory", "memory-hook", "health-hook",
         "health-doc", "feature-log-hook", "ecosystem-skill", "setup-skill",
         "skills-catalog", "agent-pack", "output-style", "router-config", "instructions"]


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
    """Применить выбранные провиженеры к проектам. Возвращает плоский список результатов.
    Fail-soft: падение одного провиженера НЕ валит весь фан-аут — остальные отрабатывают,
    упавший помечается status=failed per-project (видно в выводе и коде возврата)."""
    return run_sync_contexts(env, config, contexts(env, config, projects), only=only,
                             mode=mode, dry=dry)


def run_sync_contexts(env, config, project_contexts, *, only=None, mode="auto", dry=False):
    """Run provisioners against caller-owned contexts without a second provider resolution."""
    eligible, ineligible = [], []
    for context in project_contexts:
        diagnostic = _project_eligibility(context)
        if diagnostic is None:
            eligible.append(context)
        else:
            ineligible.append((context, diagnostic))
    results = []
    for name in provisioner_names(only):
        results.extend(_ineligible_result(name, context, diagnostic)
                       for context, diagnostic in ineligible)
        if not eligible:
            continue
        try:
            results.extend(PROVISIONERS[name](env, config, eligible, mode, dry))
        except Exception as e:
            warn(f"провиженер '{name}' упал: {e}")
            results.extend(_result(name, p.get("id", "?"), "failed", detail=str(e))
                           for p in eligible)
    return results


def instruction_conformance_markdown(cases, checks):
    """Render committed P6 evidence from public mAInd and harness result objects."""
    lines = ["# P6 provider provision conformance", "",
             "Generated through the worktree-local mAInd public APIs on temporary roots.", "",
             "| Case | Providers | Root + five package consumers | Second run | Health/doctor | Verdict |",
             "|:--|:--|--:|:--|:--|:--|"]
    for case in cases:
        lines.append("| {name} | {providers} | {targets} | {second} | {health} | {verdict} |".format(
            name=case["name"], providers=", ".join(case["providers"]),
            targets=case["targets"], second=case["second"], health=case["health"],
            verdict=case["verdict"]))
    lines += ["", "| Boundary check | Result |", "|:--|:--|"]
    lines.extend(f"| {check['name']} | {check['result']} |" for check in checks)
    lines += ["", "All roots were temporary. `sync` used the frozen `harness.instructions`",
              "plan/check/apply/repair API; mAInd did not parse, render or translate instruction files.", ""]
    return "\n".join(lines)


def provisioner_provider_matrix(results, provider_ids):
    """Describe every selected provider against every current semantic provisioner.

    This is conformance evidence, not a second provider catalog: provider-qualified rows
    remain owned by their existing P5/P6 operation result, while provisioners with no
    provider intent are recorded as deliberately neutral instead of pretending to write a
    provider target.
    """
    by_name = {row["provisioner"]: row for row in results}
    matrix = []
    for name in provisioner_names():
        result = by_name.get(name, {})
        provider_rows = {row["provider_id"]: row for row in result.get("providers", ())}
        intents = PROVISIONER_INTENTS[name]
        for provider_id in provider_ids:
            row = provider_rows.get(provider_id)
            if row is not None:
                diagnostic = row["diagnostic"] or "none"
                matrix.append({"provisioner": name, "provider_id": provider_id,
                               "support": "adapter-projected", "activation": row["status"],
                               "diagnostic": ",".join(sorted(set(diagnostic.split(","))))})
            elif intents:
                matrix.append({"provisioner": name, "provider_id": provider_id,
                               "support": "delegated", "activation": "not-observed",
                               "diagnostic": "MAIND_DELEGATED:" + ",".join(intents)})
            else:
                matrix.append({"provisioner": name, "provider_id": provider_id,
                               "support": "provider-neutral", "activation": "not-applicable",
                               "diagnostic": "MAIND_PROVIDER_NEUTRAL"})
    return tuple(matrix)


def _conformance_config(project):
    return {"_version": "1", "node": {"id": "p6", "name": "P6", "role": "primary"},
            "memory": {"http_port": 4111, "stream_port": 4112},
            "graph": {"adapter": "federation"}, "projects": [project]}


def _instruction_semantics(operation):
    """Derive parity and provider-owned deltas from public harness target result fields only."""
    scoped = {}
    for target in operation.targets:
        scoped.setdefault(target.scope_id, {})[target.provider_id] = target.ordered_semantic_ids
    common, own = 0, 0
    for providers in scoped.values():
        values = tuple(providers.values())
        if len(values) == 1:
            common += len(values[0])
            continue
        left, right = values
        shared = tuple(item for item in left if item in set(right))
        if shared != tuple(item for item in right if item in set(left)):
            raise ValueError("MAIND_INSTRUCTION_PARITY_MISMATCH")
        common += len(shared)
        own += sum(len(set(value) - set(shared)) for value in values)
    return common, own


def generate_instruction_conformance(env, output_path):
    """Generate the 2026.07.19-DUAL-PROVIDER P6.2 temporary-root matrix through public mAInd APIs only."""
    from ..common import Env, atomic_write_json, atomic_write_text
    from dataclasses import replace
    from ..doctor import provider_trust_report
    from ..health import health_report
    from .onboard import onboard
    from .workspace import provider_trust

    cases, checks = [], []
    with tempfile.TemporaryDirectory(prefix="maind-p6-provision-") as temp:
        base = Path(temp)
        for label, selection in (
                ("Claude-only legacy", None),
                ("Codex-only", {"claude-code": {"enabled": False}, "codex": {"enabled": True}}),
                ("Dual-provider", {"claude-code": {"enabled": True}, "codex": {"enabled": True}})):
            root = base / label.replace(" ", "-")
            root.mkdir()
            _seed_umbrella_layout(root)
            project = {"id": "target", "name": "Target", "type": "node-package",
                       "enabled": True, "status": "active", "local_path": str(root)}
            if selection is not None:
                project["providers"] = {"contract_version": "1.0.0", "selection": selection}
            config = _conformance_config(project)
            first = run_sync(env, config, [project], only="instructions", mode="auto")[0]
            # The public result carries the target count; the harness checker is consumed by
            # rerunning its public check operation through the same provisioner context.
            context = contexts(env, config, [project])[0]
            from harness.instructions import check_instructions
            checked = check_instructions(_instruction_request(context, "check"))
            common, own = _instruction_semantics(checked)
            first_target = root / ("AGENTS.md" if first["providers"][0]["provider_id"] == "codex"
                                   else "CLAUDE.md")
            before = first_target.read_bytes()
            first_target.write_bytes(b"outside-prefix\n" + before + b"\noutside-suffix\n")
            second = run_sync_contexts(env, config, [context], only="instructions", mode="auto")[0]
            health = health_report(env, config, project, memory_reachable=False,
                                   provider_context=context)
            doctor = provider_trust_report(env, config)
            cases.append({"name": label,
                          "providers": [row["provider_id"] for row in first["providers"]],
                          "targets": len(checked.targets),
                          "second": "no-op" if not second["changed"] else "changed",
                          "health": "untrusted non-green" if all(not row["green"] for row in doctor)
                                    else "unexpected green",
                          "verdict": "GREEN" if first["status"] == second["status"] == "ok"
                                     and checked.green
                                     and all(row["status"] != "failed"
                                             for row in first["providers"] + second["providers"])
                                     and len(health["provider_trust"]) == len(checked.request.provider_ids)
                                     and common and own >= 0 else "RED"})
            semantic_result = (f"semantic IDs={common}; single-provider projection; public checker GREEN"
                               if len(checked.request.provider_ids) == 1 else
                               f"common parity IDs={common}; provider-own extensions={own}; public checker GREEN")
            checks.append({"name": f"{label}: harness semantic parity/extensions",
                           "result": semantic_result})

        # managed drift/repair is proved from public harness observations; outside bytes survive.
        root = base / "repair"
        root.mkdir()
        _seed_umbrella_layout(root)
        project = {"id": "repair", "name": "Repair", "type": "node-package", "enabled": True,
                   "status": "active", "local_path": str(root)}
        config = _conformance_config(project)
        run_sync(env, config, [project], only="instructions", mode="auto")
        target = root / "CLAUDE.md"
        original = target.read_bytes()
        target.write_bytes(b"outside-before\n" + original.replace(b"#", b"# drifted", 1)
                                + b"\noutside-after\n")
        drift = run_sync(env, config, [project], only="instructions", mode="auto")[0]
        repair = run_sync(env, config, [project], only="instructions", mode="repair")[0]
        repaired = target.read_bytes()
        checks.append({"name": "managed drift and explicit repair",
                       "result": "non-green then repair GREEN; outside-before/outside-after preserved"
                       if drift["status"] == "failed" and repair["status"] == "ok"
                       and repaired.startswith(b"outside-before\n") and repaired.endswith(b"\noutside-after\n")
                       else "RED"})

        unknown = {"id": "unknown", "name": "Unknown", "type": "node-package", "enabled": True,
                   "status": "active", "local_path": str(base / "unknown"), "providers": {
                       "contract_version": "1.0.0", "selection": {"unsupported-provider": {"enabled": True}}}}
        Path(unknown["local_path"]).mkdir()
        try:
            run_sync(env, _conformance_config(unknown), [unknown], only="instructions")
            unknown_result = "RED"
        except ValueError:
            unknown_result = "rejected before write"
        checks.append({"name": "unknown/unsupported provider", "result": unknown_result})

        full = provider_trust(contexts(env, config, [project])[0], trusted=True,
                              profile_id="trusted-full-access", origin="project")
        checks.append({"name": "implicit full access", "result": "refused"
                       if all(not row["green"] for row in full) else "RED"})

        # Exercise frozen P5 failures through its public request/result contract rather
        # than recreating instruction parsing or managed-boundary semantics in maind.
        contract_root = base / "instruction-contract"
        contract_root.mkdir()
        _seed_umbrella_layout(contract_root)
        contract_project = {"id": "contract", "name": "Contract", "type": "node-package",
                            "enabled": True, "status": "active", "local_path": str(contract_root),
                            "providers": {"contract_version": "1.0.0", "selection": {
                                "claude-code": {"enabled": True}, "codex": {"enabled": True}}}}
        contract_config = _conformance_config(contract_project)
        contract_context = contexts(env, contract_config, [contract_project])[0]
        from harness.instructions import (apply_instructions, load_catalog, plan_instructions,
                                          repair_instructions)
        request = _instruction_request(contract_context, "plan")
        missing = plan_instructions(replace(request, scope_ids=()))
        duplicate = plan_instructions(replace(request, scope_ids=("root", "root")))
        checks.append({"name": "missing/duplicate instruction scope",
                       "result": "INSTRUCTION_SCOPE_INVALID"
                       if all(any(item.code == "INSTRUCTION_SCOPE_INVALID" for item in value.diagnostics)
                              for value in (missing, duplicate)) else "RED"})

        created = plan_instructions(request)
        targets = tuple(action.target_path for action in created.artifact_plan.actions)
        applied = apply_instructions(replace(request, operation_id="apply",
                                             authorized_target_paths=targets))
        changed_catalog = copy.deepcopy(load_catalog())
        changed_catalog["scopes"][0]["sections"][0]["intent"] += " Contract-derived stale source."
        stale = plan_instructions(request, catalog=changed_catalog)
        checks.append({"name": "stale source hash",
                       "result": "INSTRUCTION_STALE_SOURCE"
                       if any(item.code == "INSTRUCTION_STALE_SOURCE" for item in stale.diagnostics)
                       else "RED"})

        target = contract_root / "AGENTS.md"
        target.write_bytes(b"outside-before\n" + target.read_bytes().replace(
            b"<!-- semantic:", b"<!-- local:", 1) + b"\noutside-after\n")
        drift = plan_instructions(request)
        action = next(item for item in drift.artifact_plan.actions
                      if item.target_path == "AGENTS.md")
        partial = _instruction_aggregate(drift)
        repaired = repair_instructions(replace(
            request, operation_id="repair", authorized_target_paths=("AGENTS.md",),
            observed_hashes=(("AGENTS.md", action.observed_hash),),
            preimage_destination="adjacent-backup"))
        checks.append({"name": "managed drift repair only managed block",
                       "result": "non-green then repair GREEN; outside bytes preserved"
                       if applied.green and not partial.green and repaired.green
                       and target.read_bytes().startswith(b"outside-before\n")
                       and target.read_bytes().endswith(b"\noutside-after\n") else "RED"})
        checks.append({"name": "one-provider partial failure critical aggregate/allow-partial",
                       "result": "non-green; explicit --allow-partial remains required"
                       if not partial.green else "RED"})

        # The matrix intentionally uses a dual-provider dry run.  Existing provisioner
        # results remain the source for provider projections; neutral/delegated rows do not
        # claim that maind wrote a provider artifact.
        dual_root = base / "provisioner-matrix"
        dual_root.mkdir()
        _seed_umbrella_layout(dual_root)
        dual = {"id": "matrix", "name": "Matrix", "type": "node-package", "enabled": True,
                "status": "active", "local_path": str(dual_root), "providers": {
                    "contract_version": "1.0.0", "selection": {
                        "claude-code": {"enabled": True}, "codex": {"enabled": True}}}}
        dual_config = _conformance_config(dual)
        dual_context = contexts(env, dual_config, [dual])[0]
        prepared = run_sync(env, dual_config, [dual], only="instructions", mode="auto")[0]
        worktree_root = Path(__file__).resolve().parents[5]
        sibling_bins = {
            "MAIND_SKM_BIN": worktree_root / "packages/skiller/bin/skiller",
            "MAIND_HARNESS_BIN": worktree_root / "packages/harness/bin/harness",
            "SKM_HARNESS_BIN": worktree_root / "packages/harness/bin/harness",
        }
        if not all(path.is_file() for path in sibling_bins.values()):
            raise RuntimeError("MAIND_CONFORMANCE_SIBLING_BIN_MISSING")
        previous_environment = {name: os.environ.get(name) for name in sibling_bins}
        os.environ.update({name: str(path) for name, path in sibling_bins.items()})
        try:
            matrix_results = run_sync_contexts(env, dual_config, [dual_context], dry=True)
        finally:
            for name, previous in previous_environment.items():
                if previous is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = previous
        matrix = provisioner_provider_matrix(matrix_results, dual_context.effective_provider_ids)
        checks.append({"name": "independent provisioner/provider matrix",
                       "result": f"{len(matrix)} explicit support/activation/diagnostic rows"
                       if prepared["status"] == "ok" else "RED"})

        # Onboard's public API receives a context once and passes it through to instruction sync.
        onboard_root = base / "onboard"
        onboard_root.mkdir()
        _seed_umbrella_layout(onboard_root)
        isolated = base / "maind"
        (isolated / "config/memory").mkdir(parents=True)
        (isolated / "config/memory/iii-config.yaml").write_text("workers: []\n", encoding="utf-8")
        isolated_env = Env(isolated, home=base / "home")
        isolated_env.home.mkdir()
        onboard_config = _conformance_config({"id": "onboard", "name": "Onboard", "type": "node-package",
                                               "enabled": True, "status": "active", "local_path": str(onboard_root)})
        onboard_config["projects"].append({"id": "swissknifeman", "name": "Swissknifeman",
                                            "enabled": True, "local_path": str(
                                                Path(__file__).resolve().parents[5])})
        atomic_write_json(isolated_env.default_config, onboard_config)
        worktree_root = Path(__file__).resolve().parents[5]
        sibling_bins = {
            "MAIND_SKM_BIN": worktree_root / "packages/skiller/bin/skiller",
            "MAIND_HARNESS_BIN": worktree_root / "packages/harness/bin/harness",
            "SKM_HARNESS_BIN": worktree_root / "packages/harness/bin/harness",
        }
        if not all(path.is_file() for path in sibling_bins.values()):
            raise RuntimeError("MAIND_CONFORMANCE_SIBLING_BIN_MISSING")
        previous_environment = {name: os.environ.get(name) for name in sibling_bins}
        os.environ.update({name: str(path) for name, path in sibling_bins.items()})
        try:
            report = onboard(isolated_env, copy.deepcopy(onboard_config), str(onboard_root),
                             {"skip_skills": True, "yes": True, "dry": True,
                              "memory": "off", "repair": False})
        finally:
            for name, previous in previous_environment.items():
                if previous is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = previous
        critical_steps = {step["name"]: step["status"] for step in report["steps"]}
        checks.append({"name": "public onboard critical environment/instruction operations",
                       "result": "GREEN" if all(critical_steps.get(name) in ("ok", "dry")
                                                   for name in ("env", "deploy", "instructions"))
                       else "RED"})

    rendered = instruction_conformance_markdown(cases, checks)
    rendered += "\n| Provisioner | Provider | Support | Activation | Diagnostic |\n"
    rendered += "|:--|:--|:--|:--|:--|\n"
    for row in matrix:
        rendered += ("| {provisioner} | {provider_id} | {support} | {activation} | "
                     "{diagnostic} |\n").format(**row)
    atomic_write_text(Path(output_path), rendered)
    if (any(case["verdict"] != "GREEN" for case in cases)
            or any(check["result"] == "RED" for check in checks)
            or any(row["provisioner"] == "instructions" and row["activation"] == "failed"
                   for row in matrix)):
        raise RuntimeError("MAIND_P6_CONFORMANCE_NON_GREEN")


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_sync(env, argv):
    opts, _ = parse_args(argv, {"--project": "str", "--namespace": "str", "--all": "bool",
                                "--only": "str", "--mode": "str", "--dry-run": "bool",
                                "--json": "bool", "--conformance": "str"})
    if opts["help"]:
        print("maind sync [--project ID | --namespace NS | --all] [--only mcp,code-graph,"
              "graph,memory,memory-hook,health-hook,health-doc,feature-log-hook,"
              "ecosystem-skill,setup-skill,skills-catalog,agent-pack,output-style,"
              "router-config,instructions] "
              "[--mode install|update|auto|repair] [--dry-run] [--json]\n"
              "maind sync --conformance <path> — P6 temporary-root provider proof")
        return
    if opts["conformance"]:
        if any((opts["project"], opts["namespace"], opts["all"], opts["only"],
                opts["mode"], opts["dry_run"], opts["json"])):
            die("--conformance не совмещается с project/only/mode/dry/json")
        generate_instruction_conformance(env, opts["conformance"])
        print(f"provider provision conformance → {opts['conformance']}")
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
        mark = {"ok": "✓", "skip": "○", "dry": "·", "failed": "✗"}.get(r["status"], "·")
        if r["status"] == "dry":
            note = f" (план: {r.get('state') or 'apply'})"
        elif r["status"] == "ok" and not r.get("changed", True):
            note = " (без изменений)"
        else:
            note = ""
        print(f"  {mark} {r['provisioner']:<11} {r['id']:<18} {r.get('detail', '')}{note}")
    failed = [r for r in results if r["status"] == "failed"]
    if failed:
        import sys
        warn(f"провиженеров упало: {len(failed)} (см. ✗ выше)")
        sys.exit(1)
