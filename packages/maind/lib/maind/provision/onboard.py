"""maind onboard <project> — unified onboarding: skills (skiller) + connection to the brain.

Orchestrates chain: register project → skiller integrate (skills+hooks) →
maind deploy (memory+graph) → seed column. Every step standalone-safe: no neighbor - step
is skipped with a warning and onboarding continues. integrate goes BEFORE deploy/seed,
so that by the time seed already existed skills-lock.json."""
import json
import os
import sys
from pathlib import Path

from aicore.util.project import detect_project_type, docs_visibility_for
from aicore.util.term import die
from aicore.util.cli import parse_args
from aicore.util.text import sanitize
from ..config import load_config
from .deploy import deploy_project, mark_deployed
from .orchestrate import run_capability
from ..projects import get as get_project
from ..projects import write_registry


def _infer_type(path):
    """Project type by markers - single detector core (path already exists:
    _ensure_project checked is_dir before calling)."""
    return detect_project_type(path)


def _register_namespaces(config, namespaces):
    """Fills the registry `config["namespaces"]` (dict name→metadata) default entries
    for those ns, which are not there yet - setdefault, so as not to overwrite already specified metadata
    when re-onboarding (idempotent). Registry - TOP_KEYS['namespaces']=dict, NOT list;
    projects[i].namespaces — separate field (list lines), does not apply here."""
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
    """(config, project, created). New path → record synthesis (+ write_registry, if not dry).
    namespaces default - general `axioma` + yours `<id>` (several per project).
    At the same time registers these namespaces in the general registry `config["namespaces"]`, if there are any
    not yet (dict-registry, setdefault — idempotent, metadata is not overwritten)."""
    proj = get_project(config, project_or_path)
    if proj is None:
        # get_project matches ONLY by id — `maind onboard <same path>` again (not by
        # id, and by absolute path) otherwise stamps a duplicate record with the same id every time
        # (incident: loqum x3 in config.json). Add. match by local_path (normalized),
        # if the argument is similar to a real directory.
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
        die(f"project not found: '{project_or_path}' — neither id in config.json, neither directory")
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
        write_registry(env, config)
    return config, proj, True


def _wire_memory(env, config, proj, namespaces=None, mechanism="manual", dry=False):
    """Posting project memory to the selected mechanism (default `manual`):
    - **maind**: MODE=maind + SessionStart-digest injection.
    - **manual** (recommended): MCP-memory is accessed explicitly, without a start digest;
      native auto-memory is also disabled.
    - **native**: return native auto-memory Claude Code (revert hook), MODE=off.
    - **off**: memory disabled (MODE=off, native do not touch).
    Idempotent; The already connected project also completes."""
    from ..health import (apply_memory_hook, configure_manual_memory, hook_memory_mode,
                          revert_memory_hook, set_hook_memory_mode)
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
            write_registry(env, config)
    wrote = False
    skipped = None
    lp = proj.get("local_path")
    mode = {"maind": "maind", "manual": "manual", "native": "off",
            "off": "off"}.get(mechanism, "manual")
    if lp and not dry and hook_memory_mode(proj) != mode:
        status, detail = set_hook_memory_mode(proj, mode)
        wrote = status == "ok"
        if status == "skip":
            skipped = detail
    # maind → digest; manual → explicit only MCP; otherwise → native/revert.
    if mechanism == "maind":
        hook = apply_memory_hook(env, config, proj, "auto", dry)
    elif mechanism == "manual":
        hook = configure_manual_memory(env, config, proj, dry)
    else:
        hook = revert_memory_hook(env, config, proj, dry)
    return {"mechanism": mechanism, "namespaces": proj.get("namespaces"),
            "memory_env_written": wrote, "memory_env_skipped": skipped, "changed": changed,
            "memory_hook": hook.get("status")}


def onboard(env, config, project_or_path, opts):
    dry = bool(opts.get("dry"))
    steps = []
    config, proj, created = _ensure_project(env, config, project_or_path,
                                            namespaces=opts.get("namespaces"), dry=dry)
    steps.append({"name": "register", "status": "ok",
                  "detail": f"{'created' if created else 'found'} project:{proj['id']}"})

    # 0. memory: default manual MCP without starting context.
    mw = _wire_memory(env, config, proj, namespaces=opts.get("namespaces"),
                      mechanism=opts.get("memory") or "manual", dry=dry)
    steps.append({"name": "memwire", "status": "ok",
                  "detail": f"mechanism={mw['mechanism']} ns=[{','.join(mw['namespaces'] or [])}] "
                            f"hook={mw.get('memory_hook')}"})

    # 1. skiller integrate — skills + environment (integrate delegates permissions/MCP/
    # package hooks harness). standalone-safe. When --skip-skills environment anyway
    # configured directly via harness (env:apply), because integrate was not called.
    if opts.get("skip_skills"):
        steps.append({"name": "skills", "status": "skipped", "detail": "--skip-skills"})
        try:
            rc = run_capability(env, config, proj["id"], "env:apply", dry=dry)
            steps.append({"name": "env", "status": "ok" if rc == 0 else "failed",
                          "detail": f"harness permissions rc={rc}"})
        except SystemExit:
            steps.append({"name": "env", "status": "skipped",
                          "detail": "harness not available - skip"})
    else:
        extra = ["--bundle", opts.get("bundle") or "recommended"]
        # project type (== profile name skiller) → explicit --profile, to select
        # skills/presets/mcp followed the type profile, and not just the bundle defaults.
        # standalone/unknown DO NOT pass explicitly: let skiller will go to autodetect-fallback
        # (minimum set + warn), and not «will supply everything» by standalone=["*"].
        ptype = proj.get("type")
        if ptype and ptype not in ("unknown", "standalone"):
            extra += ["--profile", ptype]
        # Skills publication channel (skills only; memory/graph - individual planes):
        # connect=plugins (not in repo) · vendor=physical copy in .claude/skills (in the repo, for
        # external developers without registry access swissknifeman).
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
                          "detail": "skiller not available - skip"})

    # 1b. PAO (php/laravel-project, PHP≥8.3) — token-saving output PHP-tools;
    # onboarding invariant (SKM-AUDIT-004 P6): skill delivery ≠ installation of dependency.
    lp = proj.get("local_path")
    if lp:
        from .. import pao
        pstep = pao.apply_pao(proj, Path(os.path.expanduser(lp)),
                              interactive=sys.stdin.isatty() and not opts.get("yes"), dry=dry)
        steps.append(pstep)

    # 2. maind deploy — memory + graph (MCP-hub servers)
    # --with-code (legacy --with-graphify) is recorded as an intent in the project record so that
    # subsequent `maind sync` also rolled out the code graph (config-driven, see _mcp_run).
    want_code = opts.get("with_code") or opts.get("with_graphify")
    if want_code and not (proj.get("code") or proj.get("graphify")):
        proj["code"] = True
        if not dry:
            write_registry(env, config)
    # Reuse the same P6 project context for deployment and instruction provisioning.
    from .sync import contexts, run_sync_contexts
    project_context = contexts(env, config, [proj])[0]
    res = deploy_project(env, config, proj, targets=opts.get("targets") or None,
                         with_code=True if want_code else None, dry=dry,
                         provider_projections=project_context.provider_context.projections,
                         provider_repair=bool(opts.get("repair")))
    from .. import codegraph
    if codegraph.enabled(proj, codegraph.settings(config)):  # default .serena/project.yml
        codegraph.apply_serena_config(env, config, proj, "install", dry)
    if res is None:
        steps.append({"name": "deploy", "status": "failed", "detail": "no project path"})
    else:
        steps.append({"name": "deploy", "status": "ok",
                      "detail": f"MCP → {', '.join(res['targets'])} "
                                f"({', '.join(res['servers'])})"})
        if not dry:
            config = mark_deployed(config, proj["id"], res)
            write_registry(env, config)

    # Root and package instruction semantics are intentionally owned only by frozen P5.
    # Onboard supplies its already-effective context and explicit repair choice, then reports
    # the provider-tagged aggregate without parsing/rendering the generated files.
    instruction_mode = "repair" if opts.get("repair") else "auto"
    instruction = run_sync_contexts(env, config, [project_context], only="instructions",
                                    mode=instruction_mode, dry=dry)[0]
    steps.append({"name": "instructions",
                  # Provider-native instruction carriers belong only to the umbrella
                  # monorepo. A consumer project's explicit n/a skip is successful
                  # completion of this conditional onboarding step.
                  "status": "ok" if instruction["status"] in ("ok", "dry", "skip") else "failed",
                  "detail": instruction["detail"]})

    # 3. derive graph from sources of truth (code/docks/override/skills) → project store + index
    gstats = {}
    from ..federation import graph_disabled
    if dry:
        steps.append({"name": "graph", "status": "skipped", "detail": "--dry-run"})
    elif graph_disabled(config):
        steps.append({"name": "graph", "status": "skipped", "detail": "graph disabled"})
    else:
        from ..derive import derive_project_graph
        from ..federation import Federation, rebuild_index
        d = derive_project_graph(env, config, proj)
        rebuild_index(env, config)
        gstats = Federation(env, config).stats()
        steps.append({"name": "graph", "status": "ok",
                      "detail": f"derive {proj['id']}: {d['nodes']} nodes, "
                                f"{d['edges']} ribs (code {d['by_via']['code']}, "
                                f"doc {d['by_via']['doc']})"})

    # 3c. ecosystem-skill: guided skill with instructions about MCP-tools and connections
    from .skilldoc import apply_ecosystem_skill, apply_setup_skill
    try:
        sk = apply_ecosystem_skill(env, config, proj, "auto", dry)
        steps.append({"name": "skill",
                      "status": "ok" if sk["status"] in ("ok", "dry") else "skipped",
                      "detail": f"ecosystem-mcp ({sk.get('detail', sk['status'])})"})
    except OSError as e:
        steps.append({"name": "skill", "status": "skipped", "detail": f"template not available: {e}"})

    # 3c-bis. setup-skill: tooling decision tree (reaches external repos - governance B)
    try:
        ss = apply_setup_skill(env, config, proj, "auto", dry)
        steps.append({"name": "setup-skill",
                      "status": "ok" if ss["status"] in ("ok", "dry") else "skipped",
                      "detail": f"ecosystem-setup ({ss.get('detail', ss['status'])})"})
    except OSError as e:
        steps.append({"name": "setup-skill", "status": "skipped",
                      "detail": f"template not available: {e}"})

    # 3d. agent-pack project profile - deterministic delivery of subagents via harness
    # (without agent in loop). Pack from project.agent_pack or profile.agent_pack by type.
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
                              "detail": f"pack={pack}: harness not available"})
    else:
        steps.append({"name": "agent-pack", "status": "skipped",
                      "detail": "profile without agent_pack"})

    # 4. optional brain
    if opts.get("with_brain"):
        try:
            run_capability(env, config, proj["id"], "brain:status", dry=dry)
            steps.append({"name": "brain", "status": "ok", "detail": "brain status"})
        except SystemExit:
            steps.append({"name": "brain", "status": "skipped", "detail": "brain not available"})

    return {"project": proj["id"], "created": created, "steps": steps,
            "deployed": res is not None, "graph": gstats}


# Steps, failure to complete which means the environment is NOT installed/skills/MCP — not
# mask «green» onboarding (S9): failed or skipped due to UNAVAILABLE dependency
# → escalation to rc≠0 + ATTENTION. Conscious partial onboarding removes --allow-partial.
_CRITICAL_STEPS = {"skills", "env", "deploy", "instructions"}


def _unmet_steps(report, *, dry):
    """Critical steps not completed due to failure/unavailable dependency (not user-choice).
    B dry-run no escalation (this is a preview). skipped due to --skip-skills/we do not count outages."""
    if dry:
        return []
    out = []
    for s in report["steps"]:
        if s["name"] not in _CRITICAL_STEPS:
            continue
        if s["status"] == "failed" or (
                s["status"] == "skipped" and "not available" in (s.get("detail") or "")):
            out.append(s)
    return out


def cmd_onboard(env, argv):
    o, pos = parse_args(argv, {"--bundle": "str", "--skip-skills": "bool",
                               "--targets": "str", "--with-code": "bool",
                               "--with-graphify": "bool", "--namespace": "str",
                               "--memory": "str", "--skills-channel": "str",
                               "--with-brain": "bool", "--dry-run": "bool",
                               "--repair": "bool",
                               "--allow-partial": "bool",
                               "--yes": "bool", "--json": "bool"}, max_pos=1)
    if not pos:
        die("usage: maind onboard <project|path> [--memory manual|maind|native|off] "
            "[--skills-channel connect|vendor] [--allow-partial] "
            "[--namespace a,b] [--bundle B --yes --with-code --with-brain --dry-run]")
    config, _src = load_config(env)
    ns = [s.strip() for s in (o["namespace"] or "").split(",") if s.strip()] or None
    # Checklist: default - manual MCP without context auto-injection.
    memory = o["memory"]
    if memory and memory not in ("manual", "maind", "native", "off"):
        die(f"--memory: {memory} (valid: manual|maind|native|off)")
    if not memory and not o["yes"] and sys.stdin.isatty():
        ans = input("Project memory mechanism [manual]/maind/native/off: ").strip().lower()
        memory = ans or "manual"
        if memory not in ("manual", "maind", "native", "off"):
            memory = "manual"
    # Checklist: channel for publishing skills. ONLY CONCERNS SKILLS - memory/graph/MCP
    # are configured as usual. connect=plugins (not in repo, need registry swissknifeman);
    # vendor=physical copy in .claude/skills (are committed to the repo - for projects that
    # are given to third party developers without access to swissknifeman).
    channel = o["skills_channel"]
    if channel and channel not in ("connect", "vendor"):
        die(f"--skills-channel: {channel} (valid: connect|vendor)")
    if not channel and not o["yes"] and not o["skip_skills"] and sys.stdin.isatty():
        ans = input("Publishing skills [connect]/vendor "
                    "(connect=plugins, not in repo · vendor=physical copies in the repo for "
                    "external developers): ").strip().lower()
        channel = ans if ans in ("connect", "vendor") else "connect"
    opts = {"bundle": o["bundle"], "skip_skills": o["skip_skills"], "targets": o["targets"],
            "with_code": o["with_code"], "with_graphify": o["with_graphify"],
            "namespaces": ns, "memory": memory or "maind", "skills_channel": channel,
            "with_brain": o["with_brain"], "dry": o["dry_run"], "yes": o["yes"],
            "repair": o["repair"]}
    report = onboard(env, config, pos[0], opts)
    unmet = _unmet_steps(report, dry=opts["dry"])
    report["attention"] = [s["name"] for s in unmet]
    if o["json"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Onboarding project:{report['project']} "
              f"({'created' if report['created'] else 'updated'}):")
        for s in report["steps"]:
            mark = {"ok": "✓", "skipped": "○", "failed": "✗"}.get(s["status"], "·")
            print(f"  {mark} {s['name']:<9} {s['detail']}")
        if unmet:
            names = ", ".join(f"{s['name']} ({s['detail']})" for s in unmet)
            print(f"\n⚠ ATTENTION: critical steps not completed: {names}")
    if unmet and not o["allow_partial"]:
        die("onboarding is NOT complete (environment/skills/MCP not supplied): "
            f"{', '.join(report['attention'])}. Put harness/skiller and repeat, "
            "or run with --allow-partial.")
