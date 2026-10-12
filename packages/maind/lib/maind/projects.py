"""Node project registry (superset brain .projects.json).

Reading - from config (config.json or brain-fallback). Write - only write_config
(sole writer config.json). sync_from_brain is idempotent and preserves
maind-only fields (skills/tags/dependencies/agents/repo)."""
import json
import os
import subprocess
from pathlib import Path

from aicore.util.io import atomic_write_json
from aicore.util.partners import PartnerError, PartnerUnavailable, run_partner_json
from aicore.util.term import die, warn
from aicore.util.cli import parse_args
from .config import load_brain_projects, load_config, normalize_docs_folders
from .namespaces import in_namespace, namespaces_of

# Fields that are updated from brain with sync (rest - maind-only, save).
BRAIN_SOURCED = ("name", "local_path", "vault_path", "type", "enabled", "docs_folders")


def listing(env, config):
    """List of projects from the config (as is)."""
    return list(config.get("projects") or [])


def get(config, project_id):
    for p in config.get("projects") or []:
        if p.get("id") == project_id:
            return p
    return None


def match_cwd(env, config, cwd=None):
    """Project in whose directory we are: match cwd by local_path. None if not found
    (unlike health._target, which die'etc). Used for defaultscope MCP-server."""
    from .provision.workspace import norm_path
    cwd = norm_path(cwd or os.getcwd())
    for p in listing(env, config):
        lp = p.get("local_path")
        if not lp:
            continue
        base = norm_path(lp)
        if cwd == base or cwd.startswith(base + os.sep):
            return p
        if _same_git_worktree(cwd, base):
            return p
    return None


def _git_worktree_identity(path):
    """Return (worktree_root, common_git_dir) or None without guessing paths."""
    try:
        root = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                              check=True, capture_output=True, text=True).stdout.strip()
        common = subprocess.run(["git", "-C", str(path), "rev-parse", "--git-common-dir"],
                                check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    root = Path(root).resolve()
    common = Path(common)
    if not common.is_absolute():
        common = root / common
    return root, common.resolve()


def _same_git_worktree(left, right):
    """Accept only distinct linked worktrees sharing one Git common directory."""
    left_identity = _git_worktree_identity(left)
    right_identity = _git_worktree_identity(right)
    return bool(left_identity and right_identity
                and left_identity[0] != right_identity[0]
                and left_identity[1] == right_identity[1])


def _warn_visibility_changes(pid, cur_folders, inc_folders):
    """Warn if sync changes visibility doc-folders of an existing project. Frequent
    sign - rotten brain `.projects.json` (it must be regenerated from frontmatter
    control-notes before sync; source of truth visibility — exactly frontmatter). brain when
    it doesn't matter «wins» (field is overwritten) — warn only makes the change noticeable."""
    cur_vis = {f["id"]: f["visibility"] for f in normalize_docs_folders(cur_folders)}
    for f in normalize_docs_folders(inc_folders):
        old = cur_vis.get(f["id"])
        if old is not None and old != f["visibility"]:
            warn(f"project '{pid}': docs-folder '{f['id']}' visibility {old}→{f['visibility']} "
                 f"— if unexpected, regenerate brain .projects.json from frontmatter")


def sync_from_brain(env, config, brain_path):
    """Import/updating projects from brain .projects.json. Idempotent, merges by
    id. Returns (config, stats); config NOT recorded (does this write_config).
    Directory Source of Truth/visibility — frontmatter control-notes Brain → `.projects.json`;
    maind only reflects them (brain-fields are overwritten). When changing visibility existing
    project - warn (protection against sync from a bad cache; see `_warn_visibility_changes`)."""
    incoming = load_brain_projects(brain_path)
    existing = {p.get("id"): p for p in (config.get("projects") or [])}
    order = [p.get("id") for p in (config.get("projects") or [])]
    added = updated = 0
    for inc in incoming:
        pid = inc["id"]
        if pid in existing:
            cur = existing[pid]
            if inc.get("docs_folders") is not None:
                _warn_visibility_changes(pid, cur.get("docs_folders"), inc["docs_folders"])
            for f in BRAIN_SOURCED:
                if inc.get(f) is not None:
                    cur[f] = inc[f]
            updated += 1
        else:
            existing[pid] = inc
            order.append(pid)
            added += 1
        lp = inc.get("local_path")
        if lp and not Path(os.path.expanduser(lp)).exists():
            warn(f"project '{pid}': local path not found - {lp}")
    config["projects"] = [existing[pid] for pid in order]
    return config, {"added": added, "updated": updated, "total": len(existing)}


def write_config(env, config):
    """Sole writer config.json (atomic). _version is entered as the first key.
    mode=0o600: config.json holds node secrets (integration tokens) — should not be
    world-readable even for a short recording window."""
    out = {"_version": str(config.get("_version", "1"))}
    out.update({k: v for k, v in config.items() if k != "_version"})
    atomic_write_json(env.default_config, out, mode=0o600)


def brain_path(config):
    """Where the vault with the brain project registry lives, or None when unknown:
    integrations.brain.path → vault of the project 'brain' → the vault reported by
    `brain vault --json` (the brain module owns the vault ladder)."""
    integ = (config.get("integrations") or {}).get("brain") or {}
    p = integ.get("path") or integ.get("local_path")
    if p:
        return p
    for proj in config.get("projects") or []:
        if proj.get("id") == "brain" and proj.get("vault_path"):
            return proj["vault_path"]
    try:
        info = run_partner_json("brain", ["vault", "--json"], timeout=30)
    except (PartnerUnavailable, PartnerError) as exc:
        warn(str(exc))
        return None
    path = info.get("path") if isinstance(info, dict) else None
    if not path:
        warn("PARTNER_BAD_OUTPUT: brain vault printed no vault path")
        return None
    return os.path.expanduser(path)


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_projects(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind projects <list|status|health|sync> [--json] [--project ID] "
              "[--namespace NS] [--all] [--evidence-set FILE] "
              "[--from brain] [--path DIR]")
        return
    sub, rest = argv[0], argv[1:]
    if sub == "list":
        _cmd_list(env, rest)
    elif sub == "status":
        _cmd_status(env, rest)
    elif sub == "health":
        _cmd_health(env, rest)
    elif sub == "sync":
        _cmd_sync(env, rest)
    else:
        die(f"unknown subcommand projects: {sub} (list|status|health|sync)")


def _cmd_health(env, argv):
    """Exact-set, read-only provider health over one sealed evidence descriptor."""
    from .provider_health import evaluate, load_evidence_set

    opts, _ = parse_args(argv, {
        "--json": "bool", "--project": "str", "--namespace": "str",
        "--all": "bool", "--evidence-set": "str",
    })
    selectors = sum(bool(opts[name]) for name in ("project", "namespace", "all"))
    if opts["help"]:
        print("maind projects health [--project ID | --namespace NS | --all] "
              "--evidence-set FILE --json")
        return
    if selectors != 1:
        die("projects health: specify exactly one scope: --project, --namespace or --all")
    if not opts["evidence_set"]:
        die("projects health: required --evidence-set FILE")
    config, _src = load_config(env)
    selected = listing(env, config)
    if opts["project"]:
        selected = [item for item in selected if item.get("id") == opts["project"]]
        if not selected:
            die(f"projects health: project not found: {opts['project']}")
    elif opts["namespace"]:
        selected = [item for item in selected if in_namespace(item, opts["namespace"])]
        if not selected:
            die(f"projects health: namespace is empty or not found: {opts['namespace']}")
    try:
        evidence_set = load_evidence_set(opts["evidence_set"])
        result = evaluate(env, config, selected, evidence_set)
    except (TypeError, ValueError) as error:
        die(f"projects health: {error}")
    if opts["json"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"provider health: {result['aggregate']} · projects={len(result['projects'])}")
    for project in result["projects"]:
        print(f"  {project['project_id']}: {project['aggregate']}")


def _cmd_status(env, argv):
    from .probe import drift_hints, probe_hub, probe_project
    from .provision.workspace import trusted_dirs
    opts, _ = parse_args(argv, {"--json": "bool", "--project": "str", "--all": "bool",
                                "--namespace": "str"})
    config, _src = load_config(env)
    hub = probe_hub(env, config)
    reach = hub["memory"]["running"]
    trusted = trusted_dirs(env)
    projs = listing(env, config)
    if opts["project"]:
        projs = [p for p in projs if p.get("id") == opts["project"]]
    if opts["namespace"]:
        projs = [p for p in projs if in_namespace(p, opts["namespace"])]
    reports = [probe_project(env, config, p, memory_reachable=reach, trusted=trusted)
               for p in projs]
    for r in reports:                       # B: drift-tips «layer X → repair command»
        r["fixes"] = drift_hints(env, config, r)
    if opts["json"]:
        print(json.dumps({"hub": hub, "projects": reports}, ensure_ascii=False, indent=2))
        return
    m, g, dw = hub["memory"], hub["graph"], hub["docs_watcher"]
    print(f"Hub: memory {'up' if m['running'] else 'down'} ({m['url']}) · "
          f"graph {g['nodes']}n/{g['edges']}e · docs-watcher "
          f"{'up' if dw['running'] else 'down'}")
    print(f"Projects ({len(reports)}) — layers: mcp[a/m/c] · skills · packs(roles) · trust:")
    for r in reports:
        c = r.get("configured", {})
        mcp = ("a" if c.get("agentmemory_mcp") else "-") \
            + ("m" if c.get("maind_mcp") else "-") \
            + ("c" if c.get("code_mcp") else "-")
        sk = r.get("skills", {}).get("total", 0)
        ap = (r.get("agent_packs") or {}).get("count", 0)
        trust = "trust✓" if r.get("trusted") else "trust·"
        print(f"  {r['status']:<11} {r['id']:<18} mcp[{mcp}] {trust} "
              f"skills={sk:<3} packs={ap:<2} {r.get('memory_scope', '')}")
        for h in r.get("fixes", []):
            print(f"      ⚠ {h['layer']}: {h['issue']} → {h['fix']}")


def _cmd_list(env, argv):
    opts, _ = parse_args(argv, {"--json": "bool", "--namespace": "str"})
    config, source = load_config(env)
    projects = listing(env, config)
    if opts["namespace"]:
        projects = [p for p in projects if in_namespace(p, opts["namespace"])]
    if opts["json"]:
        print(json.dumps(projects, ensure_ascii=False, indent=2))
        return
    if not projects:
        print("no projects - create config.json from config.example.json "
              "or `maind projects sync --from brain`")
        return
    print(f"Projects ({len(projects)}, source: {source}):")
    for p in projects:
        deps = p.get("dependencies") or []
        tail = f" → deps: {', '.join(deps)}" if deps else ""
        ns = ", ".join(sorted(namespaces_of(p)))
        dis = "" if p.get("enabled", True) else " [disabled]"
        ptype = p.get("type") or "-"
        print(f"  {p.get('id', '?'):<18} {ptype:<16} {p.get('status', ''):<9}"
              f"ns[{ns}]{dis}{tail}")


# ── namespaces ───────────────────────────────────────────────────────────────
def cmd_namespaces(env, argv):
    """List namespace ecosystems: registry (section namespaces) + member projects.
    Membership source - field projects[].namespaces (no/empty → 'default')."""
    opts, _ = parse_args(argv, {"--json": "bool"})
    if opts["help"]:
        print("maind namespaces [--json]  — namespace-groups and their member projects")
        return
    config, _src = load_config(env)
    registry = config.get("namespaces") or {}
    projs = listing(env, config)
    members = {}                              # ns → [project ids] (without wildcard)
    wildcard = []                            # projects '*' — in all namespace
    for p in projs:
        ns = namespaces_of(p)
        if "*" in ns:
            wildcard.append(p["id"])
            continue
        for n in ns:
            members.setdefault(n, []).append(p["id"])
    names = sorted(set(members) | set(registry) | {"default"})
    if opts["json"]:
        out = {n: {"meta": registry.get(n, {}),
                   "members": sorted(members.get(n, [])), "wildcard": sorted(wildcard)}
               for n in names}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"Namespaces ({len(names)}):")
    for n in names:
        meta = registry.get(n) or {}
        title = f" — {meta['name']}" if meta.get("name") else ""
        mem = sorted(members.get(n, []))
        print(f"  {n:<16}{title}")
        print(f"    members: {', '.join(mem) if mem else '—'}")
    if wildcard:
        print(f"  {'*':<16} — general infrastructure (in all namespace)")
        print(f"    members: {', '.join(sorted(wildcard))}")


def _cmd_sync(env, argv):
    opts, _ = parse_args(argv, {"--from": "str", "--path": "str"})
    src = opts["from"] or "brain"
    config, _src = load_config(env)
    if src == "brain":
        path = opts["path"] or brain_path(config)
        if not path:
            die("brain vault not found: set integrations.brain.path in config.json "
                "or configure the vault with the brain module")
        config, stats = sync_from_brain(env, config, path)
        write_config(env, config)
        print(f"Sync from brain ({path}): +{stats['added']} new, "
              f"~{stats['updated']} updated, total {stats['total']}. "
              f"Recorded in {env.default_config.name}")
    elif src == "swissknifeman":
        from .derive import derive_all
        stats = derive_all(env, config)
        edges = sum(s["by_via"]["skills"] for s in stats)
        print(f"Derive skills (federation): {len(stats)} projects, "
              f"{edges} skill edges → project graphs")
    else:
        die(f"--from: brain | swissknifeman (received: '{src}')")
