"""maind sync — unified provisioning: analyze config.json and roll out the controlled
artifacts for all connected projects with ONE command.

Each artifact is a provisioner with `run(env, config, projects, mode, dry) → [result]`. Registry
PROVISIONERS + order ORDER; `--only` narrows the set. Mode (mode) sets «synchronization method
areas»: install — initial installation (create if not), update — update already
existing (drift by hash), auto — both (no→install, deprecated→update, fresh→skip).

Fan-out on projects and resolution paths/scope moved here (DRY): deploy/derive/seed/health —
providers on top of one context, rather than a duplicate loop in each module."""
from __future__ import annotations

import copy
import contextlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aicore.util.term import die, warn
from aicore.util.cli import parse_args
from aicore.artifacts.lock import LOCK_RELATIVE_PATH, parse_lock, serialize_lock
from aicore.util.io import safe_load_json
from aicore.util.partners import (PartnerError, PartnerUnavailable, partner_command,
                                  run_partner_json)
from .. import harness_link
from ..config import load_config
from ..namespaces import in_namespace
from ..projects import get as get_project
from ..projects import listing

MODES = ("install", "update", "auto", "repair")

# mAInd orders semantic work; provider adapters own native paths, trust and rendering.
# These IDs deliberately do not encode a provider target or a renderer implementation.
INTENT_ORDER = ("trust", "memory-context", "health", "skills", "agent-pack", "router",
                "instruction-root", "instruction-package")
PROVISIONER_INTENTS = {
    "mcp": (), "code-graph": (), "graph": (),
    "memory-hook": ("memory-context",), "health-hook": ("health",),
    "health-doc": ("health",), "feature-log-hook": ("health",),
    "ecosystem-skill": ("skills",), "setup-skill": ("skills",),
    "skills-catalog": ("skills",), "agent-pack": ("agent-pack",),
    "output-style": ("memory-context",), "router-config": ("router",),
    "instructions": ("instruction-root", "instruction-package"),
    "gitignore": (),
}


# ── project context (single path resolution/scope) ──────────────────────────────
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
    """Fan-out: --project <id> | --namespace <ns> | --all (enabled). The only one
    source of sample projects."""
    if opts.get("project"):
        proj = get_project(config, opts["project"])
        if proj is None:
            die(f"project not found in config.json: {opts['project']}")
        return [proj]
    if opts.get("namespace"):
        projs = [p for p in listing(env, config)
                 if p.get("enabled", True) and in_namespace(p, opts["namespace"])]
        if not projs:
            die(f"in namespace '{opts['namespace']}' no enabled-projects")
        return projs
    if opts.get("all"):
        return [p for p in listing(env, config) if p.get("enabled", True)]
    die("specify --project <id>, --namespace <ns> or --all")


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
    detail = ("no local_path" if diagnostic == "MAIND_PROJECT_LOCAL_PATH_MISSING"
              else "project path is not available")
    return _result(provisioner, context.id, "skip", state="ineligible",
                   detail=f"{detail}: {diagnostic}",
                   provider_aggregate=_ineligible_provider_aggregate(context, diagnostic))


def _result(provisioner, project_id, status, *, changed=False, state="", detail="",
            provider_aggregate=None, bootstrap_transfer=None):
    """Unified result form of the provider (same as health._result): ALL keys always
    are present, therefore CLI and tests are independent of .get()-defaults. status: ok|skip|dry."""
    result = {"provisioner": provisioner, "id": project_id, "status": status,
              "changed": changed, "state": state, "detail": detail}
    if provider_aggregate is not None:
        result["providers"] = list(provider_aggregate.rows)
        result["provider_aggregate"] = "green" if provider_aggregate.green else "non-green"
    if bootstrap_transfer is not None:
        result["bootstrap_transfer"] = bootstrap_transfer
    return result


# ── providers ──────────────────────────────────────────────────────────────
def _mcp_run(env, config, projects, mode, dry):
    """MCP-hub servers (agent-memory + maind [+ code graph/Serena]) in project configs."""
    from .deploy import deploy_project, mark_deployed, provider_operation_green
    from ..mcp_parity import repair_settings_duplicates
    from ..projects import write_registry
    results, applied = [], False
    for context in projects:
        p = context.project if isinstance(context, ProjectContext) else context
        provider_context = context.provider_context if isinstance(context, ProjectContext) else None
        local = p.get("local_path")
        if local:
            repair_settings_duplicates(local, dry=dry)
        res = deploy_project(env, config, p, dry=dry,
                             provider_projections=(provider_context.projections
                                                   if provider_context is not None else None),
                             provider_repair=(mode == "repair"))
        if res is not None and mode == "auto" and not dry and not provider_operation_green(res):
            res = deploy_project(env, config, p, dry=False,
                                 provider_projections=(provider_context.projections
                                                       if provider_context is not None else None),
                                 provider_repair=True)
        if res is None:
            results.append(_result("mcp", p["id"], "skip", detail="no/no project path"))
            continue
        changed = (res["provider_changed"] if res.get("provider_plan") is not None
                   else any(w["changed"] for w in res["written"]))
        operation_green = provider_operation_green(res)
        if not dry and operation_green:
            mark_deployed(config, p["id"], res)
            applied = True
        detail = ", ".join(res["targets"])
        if res.get("skipped"):
            detail += f" (missed broken channels: {', '.join(res['skipped'])})"
        aggregate = _provider_aggregate(res["provider_plan"]) if res.get("provider_plan") else None
        results.append(_result("mcp", p["id"], "ok" if operation_green else "failed",
                               changed=changed, detail=detail, provider_aggregate=aggregate,
                               bootstrap_transfer=res.get("bootstrap_transfer")))
    if applied:
        write_registry(env, config)
    return results


def _codegraph_run(env, config, projects, mode, dry):
    """Default .serena/project.yml to projects with code graph enabled (engine Serena)."""
    from ..codegraph import apply_serena_config
    return [apply_serena_config(env, config, p, mode, dry) for p in projects]


def _graph_run(env, config, projects, mode, dry):
    """Derive project graph from sources (composer/Brain/override) + index rebuild.
    changed — honestly on the contents of the store (serialization is deterministic), to
    --mode update did not report a change where the graph had not actually changed."""
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


def _health_hook_run(env, config, projects, mode, dry):
    """SessionStart-connection hook with the hub (DOES NOT block) in .claude/settings.json projects."""
    from ..health import apply_health_hook, revert_health_hook
    enabled = bool((config.get("observability") or {}).get("session_start_health_hook", False))
    fn = apply_health_hook if enabled else revert_health_hook
    return [fn(env, config, p, mode, dry) for p in projects]


def _memory_hook_run(env, config, projects, mode, dry):
    """SessionStart-memory DIGEST injection + disabling native auto-memory - by intent
    project from .claude/memory.env.ini: MODE=maind → set (apply_memory_hook), MODE=off →
    roll back to native (revert_memory_hook), no config → do not touch. Yes `maind sync`
    rolls out auto-loading of memory to already connected projects, without running the full onboard."""
    from ..health import (apply_memory_hook, configure_manual_memory, hook_memory_mode,
                          revert_memory_hook)
    results = []
    for p in projects:
        hmode = hook_memory_mode(p)
        if hmode == "maind":
            results.append(apply_memory_hook(env, config, p, mode, dry))
        elif hmode == "manual":
            results.append(configure_manual_memory(env, config, p, dry))
        elif hmode is not None:                       # off/native — return native memory
            results.append(revert_memory_hook(env, config, p, dry))
        else:                                         # project memory not configured
            results.append(_result("memory-hook", p["id"], "skip", state="absent",
                                   detail="no MODE in .claude/memory.env.ini — pass"))
    return results


def _health_doc_run(env, config, projects, mode, dry):
    """Managed block «PRIORITY №1 — connection with mAInd» in CLAUDE.md projects."""
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
    scopes = harness_link.instruction_scopes()["scopes"]
    root = context.path
    return tuple(scope_id for scope_id in scopes
                 if scope_id == "root" or (
                     (candidate := root / "packages" / scope_id).is_dir()
                     and not candidate.is_symlink()))


def _instruction_call(context, operation, *, authorized=(), observed=(), scope_ids=None):
    """Run one public harness instruction operation for the project; maind never reads its catalog."""
    return harness_link.run_instructions(
        operation, context.path,
        scope_ids=_instruction_scope_ids(context) if scope_ids is None else scope_ids,
        provider_ids=context.effective_provider_ids, authorized=authorized, observed=observed)


def _instruction_aggregate(operation):
    """Preserve P5 target observations as provider-tagged rows without reclassifying them."""
    rows = []
    for provider_id in operation.provider_ids:
        targets = [target for target in operation.targets if target.provider_id == provider_id]
        diagnostics = [code for target in targets for code in target.diagnostics]
        rows.append({"provider_id": provider_id,
                     "status": "planned" if not diagnostics else "failed",
                     "required": True, "diagnostic": ",".join(diagnostics) or None})
    return ProviderProvisionAggregate(tuple(rows))


def _instruction_run(env, config, projects, mode, dry):
    """Provision root plus applicable real package scopes through the harness instruction commands.

    The plan is always obtained first.  The only write authority supplied to harness is the
    exact target set returned by that plan; mAInd neither parses nor renders instructions.
    """
    results = []
    for context in projects:
        if not isinstance(context, ProjectContext) or not context.exists:
            project = context.project if isinstance(context, ProjectContext) else context
            results.append(_result("instructions", project["id"], "skip", state="absent",
                                   detail="no project path"))
            continue
        if not _instructions_applicable(context):
            results.append(_result("instructions", context.id, "skip", state="n-a",
                                   detail="only umbrella-monorepo swissknifeman"))
            continue
        try:
            planned = _instruction_call(context, "plan")
        except PartnerUnavailable as error:
            warn(str(error))
            results.append(_result("instructions", context.id, "skip", state="absent",
                                   detail="harness not available"))
            continue
        paths = planned.writable_paths()
        operation = planned
        # P5 classifies missing/stale targets as diagnostics in the no-write plan; its
        # apply command is the sole authority that decides whether those planned paths may write.
        if not dry and planned.planned:
            if mode == "repair":
                operation = _instruction_call(context, "repair", authorized=paths,
                                              observed=planned.drift_hashes())
            elif paths:
                operation = _instruction_call(context, "apply", authorized=paths)
            else:
                operation = _instruction_call(context, "check")
        aggregate = _instruction_aggregate(operation)
        changed = any(target.changed for target in operation.targets)
        status = "dry" if dry else ("ok" if operation.green else "failed")
        detail = f"{len(operation.targets)} targets; intents=instruction-root,instruction-package"
        results.append(_result("instructions", context.id, status, changed=changed,
                               state="clean" if operation.green else "non-green",
                               detail=detail, provider_aggregate=aggregate))
    return results


def _feature_log_hook_run(env, config, projects, mode, dry):
    """Retire automatic SessionEnd commit copying, including previously enabled hooks."""
    from ..health import revert_feature_log_hook
    return [revert_feature_log_hook(env, config, p, mode, dry) for p in projects]


def _setup_skill_run(env, config, projects, mode, dry):
    """Controlled skill ecosystem-setup (tooling decision tree) for projects."""
    from .skilldoc import apply_setup_skill
    return [apply_setup_skill(env, config, p, mode, dry) for p in projects]


def _ecosystem_skill_run(env, config, projects, mode, dry):
    """Controlled skill ecosystem-mcp (instructions about MCP-tools and connections) to projects."""
    from .skilldoc import apply_ecosystem_skill
    return [apply_ecosystem_skill(env, config, p, mode, dry) for p in projects]


_PROFILES_CACHE = {}


def _skiller_profiles(config):
    """Profile catalog of skiller {id: document} from `skiller profiles --json`, or {} when
    skiller is not available (agent packs then come only from the project and its roles).
    One call per distinct skiller launcher per process."""
    argv = partner_command("skiller", legacy_env=("MAIND_SKM_BIN",))
    key = tuple(argv) if argv else None
    if key in _PROFILES_CACHE:
        return _PROFILES_CACHE[key]
    profiles = {}
    try:
        doc = run_partner_json("skiller", ["profiles", "--json"],
                               legacy_env=("MAIND_SKM_BIN",), timeout=60)
        found = doc.get("profiles") if isinstance(doc, dict) else None
        if not isinstance(found, dict):
            raise PartnerError("PARTNER_BAD_OUTPUT: skiller profiles printed no profiles object")
        profiles = found
    except (PartnerUnavailable, PartnerError) as exc:
        warn(str(exc))
    _PROFILES_CACHE[key] = profiles
    return profiles


def _profile_for(config, project):
    """Profile skiller by project.type (dict) or {}."""
    ptype = project.get("type")
    if not ptype:
        return {}
    profile = _skiller_profiles(config).get(ptype)
    return profile if isinstance(profile, dict) else {}


def _resolve_agent_pack(config, project):
    """Project packs: project.agent_pack (str|list) > profile.agent_pack by project.type,
    PLUS role packs (option C): project.roles → config.role_packs[role] — cross-stack packs
    persons on top of the profile stack pack. [] — nothing defined (step will be skipped)."""
    explicit = project.get("agent_pack")
    if isinstance(explicit, str):
        packs = [explicit]
    elif isinstance(explicit, list):
        packs = list(explicit)
    else:
        pack = _profile_for(config, project).get("agent_pack")
        packs = [pack] if isinstance(pack, str) else (list(pack) if isinstance(pack, list) else [])
    # role-packs: project.roles (selected roles) → pack from config.role_packs, additive
    role_map = config.get("role_packs") or {}
    for role in (project.get("roles") or []):
        rp = role_map.get(role)
        if rp and rp not in packs:
            packs.append(rp)
    return packs


def _profile_answers(config, project):
    """Add. --answer for rendering from profile: model_tiers (role → MODEL_<ROLE>=tier).
    So the project type profile pre-fills the model ranges of the pack agents."""
    out = []
    for role, tier in (_profile_for(config, project).get("model_tiers") or {}).items():
        out += ["--answer", f"MODEL_{role.upper().replace('-', '_')}={tier}"]
    return out


def _installed_agent_packs(local_path):
    """Names of packs already settled in lock'e goals (.claude/agent-pack.lock.json). No
    file/broken JSON → empty (is interpreted as «nothing installed»)."""
    lock = safe_load_json(Path(local_path) / ".claude" / "agent-pack.lock.json", default={}) or {}
    return set((lock.get("packs") or {}).keys())


def _capability_changed(rc, dry):
    """Successful delegated dry-run only proves the successful construction of the plan.

    External CLI while they are giving the expected diff only in human-output, non-machine readable
    result. ``changed`` in sync receipt describes the applied state, so
    dry-run should not approve a mutation just because ``rc=0``.
    """
    return rc == 0 and not dry


def _agent_pack_run(env, config, projects, mode, dry):
    """Roll out deterministically agent-pack(and) project profile in .claude/ via harness
    (without agent in loop). install — only if not yet; update — version upgrade
    already installed + install missing (harness upgrade crashes on uninstalled
    package, see field-feedback: profile has grown with a new pack → update alone won't catch it);
    auto — render --auto (install + idempotent re-roll). No pack/paths/harness → skip."""
    from .orchestrate import run_capability
    results = []
    for p in projects:
        packs = _resolve_agent_pack(config, p)
        if not packs or not p.get("local_path"):
            results.append(_result("agent-pack", p["id"], "skip",
                                   detail="no profile/agent_pack or paths"))
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
                # rc!=0 — pack render failure (NOT 'skip', otherwise the failure is invisible); harness
                # not available is caught separately below as graceful skip.
                results.append(_result("agent-pack", p["id"], "ok" if rc == 0 else "failed",
                                       changed=_capability_changed(rc, dry),
                                       detail=f"pack={pack} rc={rc}"))
            except SystemExit:
                results.append(_result("agent-pack", p["id"], "skip",
                                       detail=f"pack={pack}: harness not available"))
    return results


def _skills_catalog_run(env, config, projects, mode, dry):
    """Re-resolve skill catalog (skiller update): buckets/exclude are re-read from disk
    every time, so a new skill in an already selected bucket (e.g. `pao` in `php`) arrives
    to already onboarded projects without manual re-run skiller connect/vendor/update. Idempotent,
    exclude respected, foreign-does not touch files (skillset.sync_skillset/vendor.collect_skills)."""
    from .orchestrate import run_capability
    results = []
    for p in projects:
        if not p.get("local_path"):
            results.append(_result("skills-catalog", p["id"], "skip", detail="no project path"))
            continue
        try:
            rc = run_capability(env, config, p["id"], "skm:update", dry=dry)
            results.append(_result("skills-catalog", p["id"], "ok" if rc == 0 else "failed",
                                   changed=_capability_changed(rc, dry), detail=f"rc={rc}"))
        except SystemExit:
            results.append(_result("skills-catalog", p["id"], "skip",
                                   detail="skiller not available"))
    return results


def _output_style_run(env, config, projects, mode, dry):
    """outputStyle=lean (terce-agent-voice, token-saving) in everything.claude/settings.local.json
    of already onboarded projects - catching up `skiller integrate`, which only puts this on
    NEW onboardings. Wholesale-out per-project: project.output_style="off" — then pass (not
    touch the locally selected style): block_output_style in harness OVERWRITES the key if
    it differs from the desired one, so without opt-out regular `maind sync --all` would overwrite
    someone's conscious choice."""
    from .orchestrate import run_capability
    results = []
    for p in projects:
        style = p.get("output_style", "lean")
        if not style or style == "off":
            results.append(_result("output-style", p["id"], "skip",
                                   detail="project.output_style=off"))
            continue
        if not p.get("local_path"):
            results.append(_result("output-style", p["id"], "skip", detail="no project path"))
            continue
        try:
            rc = run_capability(env, config, p["id"], "env:hooks",
                                ["--output-style", style], dry=dry)
            results.append(_result("output-style", p["id"], "ok" if rc == 0 else "failed",
                                   changed=_capability_changed(rc, dry),
                                   detail=f"style={style} rc={rc}"))
        except SystemExit:
            results.append(_result("output-style", p["id"], "skip",
                                   detail="harness not available"))
    return results


def _router_config_run(env, config, projects, mode, dry):
    """Generate/update directory intent-router (.claude/agent-router.config.json) via
    harness — ONLY for projects where the hook is already enabled (opt-in: yes agent-router.env.ini with
    POLICY!=off; turns on `harness hooks --router` / `maind onboard`). Not enabled/no path/
    harness not available → graceful skip. Comes after agent-pack (reads newly delivered agents)."""
    from .orchestrate import run_capability
    results = []
    for p in projects:
        lp = p.get("local_path")
        if not lp:
            results.append(_result("router-config", p["id"], "skip", detail="no path"))
            continue
        envini = Path(os.path.expanduser(lp)) / ".claude" / "agent-router.env.ini"
        try:
            enabled = "POLICY=off" not in envini.read_text(encoding="utf-8").replace(" ", "")
        except Exception:
            enabled = False
        if not enabled:
            results.append(_result("router-config", p["id"], "skip",
                                   detail="intent-router not enabled (opt-in)"))
            continue
        try:
            rc = run_capability(env, config, p["id"], "env:router", [], dry=dry)
            results.append(_result("router-config", p["id"], "ok" if rc == 0 else "failed",
                                   changed=_capability_changed(rc, dry), detail=f"rc={rc}"))
        except SystemExit:
            results.append(_result("router-config", p["id"], "skip",
                                   detail="harness not available"))
    return results


def _gitignore_run(env, config, projects, mode, dry):
    """Append `.gitignore` lines for service files that already exist.

    Runs last so files written earlier in the same sync are visible. Every mode
    appends missing patterns; nothing is removed and `git rm --cached` is not run.
    """
    from aicore.state.gitignore import PolicyError, apply_recommendations
    results = []
    for context in projects:
        project = context.project if isinstance(context, ProjectContext) else context
        project_id = project.get("id", "?")
        local = project.get("local_path")
        if not local:
            results.append(_result("gitignore", project_id, "skip", detail="no project path"))
            continue
        root = Path(os.path.expanduser(local))
        if not root.is_dir():
            results.append(_result("gitignore", project_id, "skip",
                                   detail="project path is not available"))
            continue
        try:
            outcome = apply_recommendations(root, dry=dry)
        except PolicyError as exc:
            results.append(_result("gitignore", project_id, "failed", detail=str(exc)))
            continue
        if outcome["status"] == "skip":
            results.append(_result("gitignore", project_id, "skip", detail=outcome["detail"]))
            continue
        if not dry and outcome["tracked"]:
            warn(f"{project_id}: .gitignore now lists the pattern, but these files stay tracked "
                 f"until git rm --cached: {', '.join(outcome['tracked'])}")
        results.append(_result("gitignore", project_id, "ok",
                               changed=bool(outcome["added"]) and not dry,
                               detail=outcome["detail"]))
    return results


# Register of providers and application procedure (ORDER specifies the sequence).
# Signature of each: run(env, config, projects, mode, dry) -> list[_result(...)]
# (result form - _result above: provisioner/id/status/changed/state/detail).
PROVISIONERS = {
    "mcp": _mcp_run,
    "code-graph": _codegraph_run,
    "graph": _graph_run,
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
    "gitignore": _gitignore_run,
}
ORDER = ["mcp", "code-graph", "graph", "memory-hook", "health-hook",
         "health-doc", "feature-log-hook", "ecosystem-skill", "setup-skill",
         "skills-catalog", "agent-pack", "output-style", "router-config",
         "instructions", "gitignore"]


def provisioner_names(only=None):
    """Provider names are ok ORDER, limited --only (csv) and the registry."""
    if only:
        want = [x.strip() for x in only.split(",") if x.strip()]
        for x in want:
            if x not in PROVISIONERS:
                die(f"unknown provider: {x} (is: {', '.join(sorted(PROVISIONERS))})")
        return [n for n in ORDER if n in want]
    return [n for n in ORDER if n in PROVISIONERS]


def run_sync(env, config, projects, *, only=None, mode="auto", dry=False):
    """Apply selected providers to projects. Returns a flat list of results.
    Fail-soft: the fall of one provider does NOT bring down the entire fan-out - the rest are worked out,
    fallen is marked status=failed per-project (visible in output and return code)."""
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
            warn(f"provider '{name}' fell: {e}")
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


@contextlib.contextmanager
def _json_stdout_boundary(enabled):
    """Keep provider subprocess chatter off the single-document JSON stdout contract."""
    if not enabled:
        yield
        return
    stdout_fd = sys.stdout.fileno()
    saved_stdout = os.dup(stdout_fd)
    try:
        sys.stdout.flush()
        os.dup2(sys.stderr.fileno(), stdout_fd)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved_stdout, stdout_fd)
        os.close(saved_stdout)


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
    """Generate the temporary-root matrix through public mAInd APIs only."""
    from ..common import Env
    from aicore.util.io import atomic_write_json, atomic_write_text
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
            checked = _instruction_call(context, "check")
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
                                     and len(health["provider_trust"]) == len(checked.provider_ids)
                                     and common >= 0 and own >= 0 else "RED"})
            semantic_result = (f"semantic IDs={common}; single-provider projection; public checker GREEN"
                               if len(checked.provider_ids) == 1 else
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
        # An unknown scope and a repeated scope are the closed scope-set violations the command can express.
        missing = _instruction_call(contract_context, "plan", scope_ids=("no-such-scope",))
        duplicate = _instruction_call(contract_context, "plan", scope_ids=("root", "root"))
        checks.append({"name": "missing/duplicate instruction scope",
                       "result": "INSTRUCTION_SCOPE_INVALID"
                       if all("INSTRUCTION_SCOPE_INVALID" in value.diagnostics
                              for value in (missing, duplicate)) else "RED"})

        created = _instruction_call(contract_context, "plan")
        applied = _instruction_call(contract_context, "apply", authorized=created.writable_paths())
        # A stale source is a lock record whose recorded source no longer matches the catalog:
        # forge exactly that in the temporary root and ask harness to plan again.
        lock_path = contract_root / LOCK_RELATIVE_PATH
        genuine_lock = lock_path.read_bytes()
        forged = parse_lock(genuine_lock)
        lock_path.write_bytes(serialize_lock(replace(forged, records=(
            replace(forged.records[0], source_hash="sha256:" + "0" * 64),) + forged.records[1:])))
        stale = _instruction_call(contract_context, "plan")
        lock_path.write_bytes(genuine_lock)
        checks.append({"name": "stale source hash",
                       "result": "INSTRUCTION_STALE_SOURCE"
                       if "INSTRUCTION_STALE_SOURCE" in stale.diagnostics
                       else "RED"})

        target = contract_root / "AGENTS.md"
        target.write_bytes(b"outside-before\n" + target.read_bytes().replace(
            b"<!-- semantic:", b"<!-- local:", 1) + b"\noutside-after\n")
        drift = _instruction_call(contract_context, "plan")
        partial = _instruction_aggregate(drift)
        repaired = _instruction_call(contract_context, "repair", authorized=("AGENTS.md",),
                                     observed=drift.drift_hashes())
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
        matrix_results = run_sync_contexts(env, dual_config, [dual_context], dry=True)
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
        hub_root = base / "swissknifeman"
        hub_root.mkdir()
        _seed_umbrella_layout(hub_root)
        onboard_config["projects"].append({"id": "swissknifeman", "name": "Swissknifeman",
                                            "enabled": True, "local_path": str(hub_root)})
        atomic_write_json(isolated_env.legacy_node_config, onboard_config)
        report = onboard(isolated_env, copy.deepcopy(onboard_config), str(onboard_root),
                         {"skip_skills": True, "yes": True, "dry": True,
                          "memory": "off", "repair": False})
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
              "graph,memory-hook,health-hook,health-doc,feature-log-hook,"
              "ecosystem-skill,setup-skill,skills-catalog,agent-pack,output-style,"
              "router-config,instructions] "
              "[--mode install|update|auto|repair] [--dry-run] [--json]\n"
              "maind sync --conformance <path> — P6 temporary-root provider proof")
        return
    if opts["conformance"]:
        if any((opts["project"], opts["namespace"], opts["all"], opts["only"],
                opts["mode"], opts["dry_run"], opts["json"])):
            die("--conformance is not compatible with project/only/mode/dry/json")
        generate_instruction_conformance(env, opts["conformance"])
        print(f"provider provision conformance → {opts['conformance']}")
        return
    mode = opts["mode"] or "auto"
    if mode not in MODES:
        die(f"--mode: {', '.join(MODES)} (received: {mode})")
    config, _src = load_config(env)
    projects = select_projects(env, config, opts)
    # Provisioners use their public CLIs and may report normal diagnostics to stdout.
    # Redirect the file descriptor too: subprocesses inherit it, unlike Python's stdout object.
    with _json_stdout_boundary(opts["json"]):
        results = run_sync(env, config, projects, only=opts["only"], mode=mode,
                           dry=opts["dry_run"])
    failed = [r for r in results if r["status"] == "failed"]
    if opts["json"]:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        if failed:
            sys.exit(1)
        return
    tag = "[dry-run] " if opts["dry_run"] else ""
    print(f"{tag}sync (mode={mode}, projects {len(projects)}, "
          f"providers: {', '.join(provisioner_names(opts['only']))})")
    for r in results:
        mark = {"ok": "✓", "skip": "○", "dry": "·", "failed": "✗"}.get(r["status"], "·")
        if r["status"] == "dry":
            note = f" (plan: {r.get('state') or 'apply'})"
        elif r["status"] == "ok" and not r.get("changed", True):
            note = " (no changes)"
        else:
            note = ""
        print(f"  {mark} {r['provisioner']:<11} {r['id']:<18} {r.get('detail', '')}{note}")
    if failed:
        warn(f"providers fell: {len(failed)} (see ✗ above)")
        sys.exit(1)
