"""maind health — client healthcheck project connection with the hub (memory + maind MCP).

Run FROM the project (--cwd) or by id (--project). DOES NOT block: always prints status
connected|partial|standalone and tips. --fix picks up memory and adds MCP-servers.

Here are the delivery providers «priority №1» to projects (are called from sync):
- health-doc  — managed block priority-block.md in <project>/CLAUDE.md (idempotent, by hash);
- health-hook — SessionStart-hook in <project>/.claude/settings.json + copy of the script (blued).
Source of truth - templates/health/* in the maind; mode install/update/auto sets «area»."""
import copy
import json
import os
import stat
from pathlib import Path

from aicore.util.http import HTTPUnauthorizedError

from aicore.util.io import atomic_write_json, atomic_write_text, backup_file
from aicore.util.block import content_hash, upsert_block
from aicore.util.term import die, warn
from aicore.util.cli import parse_args
from .config import load_config
from .mcpconfig import check_hygiene
from .memory import auth_headers, resolve_secret
from .memory import forget as mem_forget
from .memory import health as mem_health
from .memory import recall as mem_recall
from .memory import resolve_ports
from .memory import store as mem_store
from .namespaces import namespaces_of, private_scope
from .probe import probe_project
from .projects import get as get_project
from .projects import match_cwd
from .provision.workspace import load_settings

BLOCK_MARKER = "maind:healthcheck"
HOOK_SCRIPT = ".claude/maind-health.sh"
FEATURE_HOOK_SCRIPT = ".claude/maind-feature-log.sh"
MEMORY_HOOK_SCRIPT = ".claude/maind-memory.sh"


def _status(ok: bool) -> str:
    """Check line label for cmd_health."""
    return "ok  " if ok else "FAIL"


# ── templates ──────────────────────────────────────────────────────────────────
def _render(env, relpath, subst):
    """Read template <maind>/templates/<relpath> and substitute {{KEY}} → value."""
    text = (env.root / "templates" / relpath).read_text(encoding="utf-8")
    for k, v in subst.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


# Path to launcher maind is no longer substituted in hook scripts: templates resolve it
# in runtime (env MAIND_BIN → PATH), so that the artifact does not contain machine-specific
# absolute path. See templates/health/*.sh.


# ── memory and hook mode test ───────────────────────────────────────────────
def hook_memory_mode(project):
    """MODE from <project>/.claude/memory.env.ini (memory hook mode) or None.
    Source of Truth «intentions» project memory - read and health, and sync (memory-hook)."""
    lp = project.get("local_path")
    if not lp:
        return None
    f = Path(os.path.expanduser(lp)) / ".claude" / "memory.env.ini"
    if not f.is_file():
        return None
    for line in f.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("MODE="):
            return s.split("=", 1)[1].split("#")[0].strip().strip("\"'")
    return None


def _native_memory_state(project):
    """(native_off, digest_hook_wired) from <project>/.claude/settings.json — for MODE=maind
    native auto-memory must be disabled and SessionStart-digest injection is in place."""
    lp = project.get("local_path")
    if not lp:
        return (None, None)
    settings, _ = load_settings(Path(os.path.expanduser(lp)) / ".claude" / "settings.json")
    native_off = settings.get("autoMemoryEnabled") is False
    cmds = [h.get("command", "") for g in (settings.get("hooks") or {}).get("SessionStart", [])
            for h in g.get("hooks", [])]
    return (native_off, any("maind-memory" in c for c in cmds))


def memory_roundtrip(env, config, project, memory_reachable):
    """Prove that memory REALLY works: write→recall→forget by temp-fact in private
    scope. Catches the split (hook writes to the wrong side), broken forget and loss of insulation.
    401 differs from other failures separately (findings §2: /agentmemory/health not 401'etc.
    therefore «not available» and «unauthorized» are indistinguishable without a real protected call -
    does exactly that here store/recall/forget)."""
    if not memory_reachable:
        return {"ok": False, "detail": "daemon not running"}
    _, _, url = resolve_ports(env, config)
    headers = auth_headers(resolve_secret(env, config))
    scope = private_scope(project)
    token = f"maind-health-probe-{project['id']}"
    try:
        res = mem_store(url, scope, "health-probe", token, headers=headers)
        mid = (res.get("memory") or {}).get("id") if isinstance(res, dict) else None
        found = any(token in (r.get("text") or "")
                    for r in mem_recall(url, scope, token, headers=headers))
        if mid:
            mem_forget(url, scope, mid, headers=headers)          # purely for yourself
        return {"ok": bool(found),
                "detail": scope if found else "entry not found when recall (split store?)"}
    except HTTPUnauthorizedError:
        return {"ok": False, "detail": "unauthorized (401) — check memory secret"}
    except RuntimeError as e:
        return {"ok": False, "detail": str(e)}


# ── report ────────────────────────────────────────────────────────────────────
def health_report(env, config, project, *, memory_reachable=None, provider_context=None,
                  deep=False):
    """Project communication status; mutating round-trip is only executed in deep-mode."""
    pid = project["id"]
    if memory_reachable is None:
        _, _, url = resolve_ports(env, config)
        memory_reachable = mem_health(url)
    rep = probe_project(env, config, project, memory_reachable=memory_reachable,
                        provider_context=provider_context)
    c = rep.get("configured", {})
    hook_mode = hook_memory_mode(project)
    native_off, digest_hook = _native_memory_state(project)
    roundtrip = (memory_roundtrip(env, config, project, memory_reachable) if deep
                 else {"ok": None, "detail": "missing (use --deep)"})
    local = project.get("local_path")
    hygiene = check_hygiene(os.path.expanduser(local)) if local else []
    hints = []
    if not memory_reachable:
        hints.append("memory daemon not running → maind start --only memory")
    if hook_mode not in ("maind", "manual"):
        hints.append(f"project memory not configured → maind onboard {pid} --memory manual")
    elif hook_mode == "maind" and not (native_off and digest_hook):
        hints.append("MODE=maind, but native-memory not turned off / no digest-injection → "
                     f"maind onboard {pid} --memory maind")
    elif hook_mode == "manual" and not native_off:
        hints.append("MODE=manual, but native-memory enabled → "
                     f"maind onboard {pid} --memory manual")
    if deep and not roundtrip["ok"] and memory_reachable:
        hints.append(f"memory fails round-trip ({roundtrip['detail']}) — "
                     "remember/recall go to different stores?")
    if not c.get("maind_mcp"):
        hints.append(f"no maind MCP in the project → maind sync --only mcp --project {pid}")
    for issue in hygiene:
        f = issue["file"]
        if "tracked-in-git" in issue["problems"]:
            hints.append(f"{f} is committed to git (should only be .example) → "
                         f"git rm --cached {f} (the file will remain on disk)")
        if "missing-example" in issue["problems"]:
            hints.append(f"no {f}.example → maind sync --only mcp --project {pid} "
                         "(emits a portable template + .gitignore; repairs only if "
                         "provider project plan green - failed unmanaged-target "
                         "will not receive an issue)")
    result = {
        "id": pid, "scope": rep.get("memory_scope", f"project:{pid}"),
        "namespaces": sorted(namespaces_of(project)),
        "status": rep.get("status", "standalone"),
        "memory_daemon": memory_reachable,
        "hook_memory_mode": hook_mode,
        "native_memory_off": native_off,
        "digest_hook": digest_hook,
        "memory_roundtrip": roundtrip["ok"],
        "agentmemory_mcp": bool(c.get("agentmemory_mcp")),
        "maind_mcp": bool(c.get("maind_mcp")),
        "code_mcp": bool(c.get("code_mcp")),
        "mcp_hygiene": hygiene,
        "path": rep.get("path"), "hints": hints,
    }
    if "provider_trust" in rep:
        result["provider_trust"] = rep["provider_trust"]
    return result


def _target(env, config, opts):
    """Target project: --project <id> | --cwd (match cwd by local_path) | default = cwd."""
    if opts.get("project"):
        proj = get_project(config, opts["project"])
        if proj is None:
            die(f"project not found in config.json: {opts['project']}")
        return proj
    proj = match_cwd(env, config)
    if proj is None:
        die("could not determine the project from the current directory - please specify --project <id>")
    return proj


# ── providers (are called from sync) ─────────────────────────────────────────
def _act(mode, state):
    """Is it necessary to use this mode and artifact state (absent/stale/fresh)."""
    if state == "fresh":
        return False
    if mode == "install":
        return state == "absent"
    if mode == "update":
        return state == "stale"
    return True  # auto


def _result(pid, name, state, applied, dry, detail=""):
    status = "dry" if dry and applied else ("ok" if applied else "skip")
    return {"provisioner": name, "id": pid, "status": status,
            "changed": applied and not dry, "state": state, "detail": detail}


def apply_health_doc(env, config, project, mode, dry):
    """Managed block priority-block.md in <project>/CLAUDE.md."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, "health-doc", "absent", False, dry, "no path")
    block = _render(env, "health/priority-block.md",
                    {"SCOPE": project.get("memory_scope") or f"project:{pid}",
                     "PROJECT": pid})
    claude = path / "CLAUDE.md"
    text = claude.read_text(encoding="utf-8") if claude.is_file() else ""
    new_text, _changed, state = upsert_block(text, block, BLOCK_MARKER)
    if not _act(mode, state):
        return _result(pid, "health-doc", state, False, dry, "CLAUDE.md")
    if not dry:
        if claude.is_file():
            backup_file(claude)
        atomic_write_text(claude, new_text)
    return _result(pid, "health-doc", state, True, dry, "CLAUDE.md")


def _file_state(path, content):
    if not path.is_file():
        return "absent"
    try:
        cur = path.read_text(encoding="utf-8")
    except OSError:
        return "absent"
    return "fresh" if content_hash(cur) == content_hash(content) else "stale"


def _merge_session_hook(settings, command, event="SessionStart", marker="maind-health"):
    """Idempotently add/update hook maind (by marker in the command) to event event."""
    hooks = settings.setdefault("hooks", {})
    sessions = hooks.setdefault(event, [])
    for group in sessions:
        for h in group.get("hooks", []):
            if marker in h.get("command", ""):
                if h["command"] != command:
                    h["command"] = command
                    return settings, True
                return settings, False
    sessions.append({"hooks": [{"type": "command", "command": command}]})
    return settings, True


def _remove_script_hook(project, dry, *, name, script_rel, event, marker, detail):
    """Remove a managed hook registration and script while preserving other hooks."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, name, "absent", False, dry, "no path")
    settings_path = path / ".claude" / "settings.json"
    settings, existed = load_settings(settings_path)
    changed = False
    groups = (settings.get("hooks") or {}).get(event) or []
    kept_groups = []
    for group in groups:
        hooks = [h for h in group.get("hooks", []) if marker not in h.get("command", "")]
        if len(hooks) != len(group.get("hooks", [])):
            changed = True
        if hooks:
            kept_groups.append({**group, "hooks": hooks})
    if changed:
        settings["hooks"][event] = kept_groups
        if not kept_groups:
            settings["hooks"].pop(event, None)
    script_path = path / script_rel
    if script_path.exists():
        changed = True
    if changed and not dry:
        if existed:
            backup_file(settings_path)
            atomic_write_json(settings_path, settings)
        script_path.unlink(missing_ok=True)
    return _result(pid, name, "stale" if changed else "fresh", changed, dry, detail)


def _apply_script_hook(env, project, mode, dry, *, name, template, script_rel, detail,
                       skip_detail=".claude/", subst=None, event="SessionStart",
                       marker="maind-health", render_safe=False, extra_stale=None,
                       on_settings=None):
    """Idempotent skeleton hook-progenera: template render → status (absent/stale/fresh
    subject to availability/drift hook in .claude/settings.json) → _act(mode) → backup+script entry
    (chmod +x) → merge hook in settings. Options for provisioner discrepancies:
    render_safe — template may be missing (standalone-safe → absent);
    extra_stale(settings)->bool — add. deprecation trigger (e.g. native-memory not turned off);
    on_settings(merged)->bool — edit settings before recording + sign «dirty» (forces entry)."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, name, "absent", False, dry, "no path")
    try:
        script = _render(env, template, subst or {})
    except OSError as e:                         # template not available (standalone-safe)
        if render_safe:
            return _result(pid, name, "absent", False, dry, f"template not available: {e}")
        raise
    script_path = path / script_rel
    state = _file_state(script_path, script)
    settings_path = path / ".claude" / "settings.json"
    command = f"bash {script_path}"
    settings, _existed = load_settings(settings_path)
    # trial (on copy) hook entry: state = the script is outdated OR the hook is not yet in the settings
    _, hook_changed = _merge_session_hook(copy.deepcopy(settings), command,
                                          event=event, marker=marker)
    if state == "fresh" and (hook_changed or (extra_stale(settings) if extra_stale else False)):
        state = "stale"
    if not _act(mode, state):
        return _result(pid, name, state, False, dry, skip_detail)
    if not dry:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        if script_path.is_file():
            backup_file(script_path)
        atomic_write_text(script_path, script)
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        merged, changed = _merge_session_hook(settings, command, event=event, marker=marker)
        if on_settings and on_settings(merged):
            changed = True
        if changed:
            if settings_path.is_file():
                backup_file(settings_path)
            atomic_write_json(settings_path, merged)
    return _result(pid, name, state, True, dry, detail)


def apply_health_hook(env, config, project, mode, dry):
    """SessionStart-script + write hook to <project>/.claude/settings.json."""
    return _apply_script_hook(
        env, project, mode, dry, name="health-hook",
        template="health/session-start-hook.sh", script_rel=HOOK_SCRIPT,
        detail=".claude/maind-health.sh + settings")


def revert_health_hook(env, config, project, mode, dry):
    return _remove_script_hook(project, dry, name="health-hook", script_rel=HOOK_SCRIPT,
                               event="SessionStart", marker="maind-health",
                               detail="SessionStart health disabled")


def revert_feature_log_hook(env, config, project, mode, dry):
    return _remove_script_hook(project, dry, name="feature-log-hook",
                               script_rel=FEATURE_HOOK_SCRIPT, event="SessionEnd",
                               marker="maind-feature-log",
                               detail="autopublishing of commits is disabled")


def apply_memory_hook(env, config, project, mode, dry):
    """SessionStart-memory digest injection hook (additionalContext) + disable NATIVE
    auto-memory (`autoMemoryEnabled:false`). Set for projects on `MODE=maind`: maind
    becomes the context source instead native MEMORY.md (gives auto-loading, which
    otherwise there is no demon). Idempotent. Doubles «not-maind» path does revert — `revert_memory_hook`."""
    def _disable_native(merged):
        merged["autoMemoryEnabled"] = False          # disable native auto-memory
        return True                                  # settings are always appended
    return _apply_script_hook(
        env, project, mode, dry, name="memory-hook",
        template="health/memory-digest-hook.sh", script_rel=MEMORY_HOOK_SCRIPT,
        marker="maind-memory", render_safe=True,
        extra_stale=lambda s: s.get("autoMemoryEnabled") is not False,
        on_settings=_disable_native, skip_detail=".claude/ (native off + digest)",
        detail=".claude/maind-memory.sh + autoMemoryEnabled:false")


def revert_memory_hook(env, config, project, dry):
    """Rollback to native memory: remove SessionStart-injection hook and return auto-memory
    (`autoMemoryEnabled` remove). For projects that have left `MODE=maind` on native."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, "memory-hook", "absent", False, dry, "no path")
    settings_path = path / ".claude" / "settings.json"
    settings, existed = load_settings(settings_path)
    changed = False
    sessions = (settings.get("hooks") or {}).get("SessionStart") or []
    for group in sessions:
        kept = [h for h in group.get("hooks", []) if "maind-memory" not in h.get("command", "")]
        if len(kept) != len(group.get("hooks", [])):
            group["hooks"] = kept
            changed = True
    if settings.pop("autoMemoryEnabled", None) is not None:
        changed = True
    if changed and not dry and existed:
        backup_file(settings_path)
        atomic_write_json(settings_path, settings)
    return _result(pid, "memory-hook", "stale" if changed else "fresh", changed, dry,
                   "native restored")


def configure_manual_memory(env, config, project, dry):
    """Keep mAInd available through MCP, remove digest injection, keep native auto-memory off."""
    result = _remove_script_hook(project, dry, name="memory-hook",
                                 script_rel=MEMORY_HOOK_SCRIPT, event="SessionStart",
                                 marker="maind-memory", detail="manual MCP mode")
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return result
    settings_path = path / ".claude" / "settings.json"
    settings, existed = load_settings(settings_path)
    native_changed = settings.get("autoMemoryEnabled") is not False
    if native_changed and not dry:
        settings["autoMemoryEnabled"] = False
        if existed:
            backup_file(settings_path)
        atomic_write_json(settings_path, settings)
    if native_changed:
        result["changed"] = not dry
        result["status"] = "dry" if dry else "ok"
        result["state"] = "stale"
    return result


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_health(env, argv):
    opts, _ = parse_args(argv, {"--project": "str", "--cwd": "bool", "--fix": "bool",
                                "--strict": "bool", "--json": "bool", "--deep": "bool"})
    if opts["help"]:
        print("maind health [--project ID | --cwd] [--fix] [--strict] [--deep] [--json]")
        return
    config, _src = load_config(env)
    project = _target(env, config, opts)
    from .provision.sync import contexts
    context = contexts(env, config, [project])[0]
    rep = health_report(env, config, project, provider_context=context, deep=opts["deep"])

    hygiene_fixable = any("missing-example" in i["problems"] for i in rep["mcp_hygiene"])
    if opts["fix"] and (rep["status"] != "connected" or hygiene_fixable):
        if not rep["memory_daemon"]:
            try:
                from .memory import start as mem_start
                mem_start(env, config)
            except SystemExit as e:
                warn(f"failed to raise memory: {e}")
        from .provision.sync import run_sync
        run_sync(env, config, [project], only="mcp")
        rep = health_report(env, config, project, provider_context=context, deep=opts["deep"])

    if opts["json"]:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _, _, url = resolve_ports(env, config)
        icon = {"connected": "✓", "partial": "⚠", "standalone": "✗"}.get(rep["status"], "·")
        print(f"{icon} mAInd health — project:{rep['id']} (scope {rep['scope']})")
        print(f"  [{_status(rep['memory_daemon'])}] memory daemon ({url})")
        print(f"  [{_status(rep['maind_mcp'])}] maind MCP in the project")
        print(f"  [{_status(rep['hook_memory_mode'] == 'maind')}] memory hook MODE=maind "
              f"({rep['hook_memory_mode'] or 'not specified'})")
        if rep['hook_memory_mode'] == 'maind':
            print(f"  [{_status(rep['native_memory_off'] and rep['digest_hook'])}] native off + "
                  "digest-injection (SessionStart)")
        if opts["deep"]:
            print(f"  [{_status(rep['memory_roundtrip'])}] memory round-trip (write→recall→forget)")
        else:
            print("  [skip] memory round-trip (only --deep)")
        print(f"  [{_status(not rep['mcp_hygiene'])}] config-hygiene .mcp.json "
              "(real gitignored + .example in the repo)")
        print(f"  ns: [{', '.join(rep['namespaces'])}]  status: {rep['status']}")
        for row in rep.get("provider_trust", ()):
            print(f"  [{_status(row['green'])}] provider:{row['provider_id']} trust"
                  + (f" ({', '.join(row['diagnostics'])})" if row["diagnostics"] else ""))
        for h in rep["hints"]:
            print(f"    → {h}")
    # strict crashes if connection is not connected, memory fails round-trip
    # or the trust of any included/mandatory provider not confirmed.
    trust_failed = any(not row["green"] for row in rep.get("provider_trust", ()))
    deep_failed = opts["deep"] and not rep["memory_roundtrip"]
    if opts["strict"] and (rep["status"] != "connected" or deep_failed or trust_failed):
        raise SystemExit(1)
