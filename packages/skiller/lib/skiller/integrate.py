"""integrate — integration wizard swissknifeman to the project.

Checklist going through «choose what you want from the maximum functionality» and applies
selected, reusing existing commands: do_connect/do_vendor (skills),
generate_hub (hub). Environment Claude Code (permissions/MCP/auto-approve/memory)
belongs to the host's environment tool (host commands `environment`, `permissions`) —
the corresponding blocks are delegated to it via subprocess. Safe: --dry-run,
merge-only, confirm.

Blocks: prerequisites → skills → permissions → MCP → auto-approve → memory → output-style →
plans-dir → hub → brain. Skill blocks (skills/hub) — here; environment (permissions/MCP/
auto-approve/memory/output-style/plans-dir) — in the host environment tool.
"""
import subprocess
import sys

from .common import apply_permissions, host_command_text, host_install_suffix
from aicore.util.cli import parse_flags
from aicore.util.term import die, warn
from .host import host_command
from .config import (autodetect, load_config, load_profile, resolve_profile_name,
                     resolve_target)
from .connect import do_connect
from .vendor import do_vendor
from .skillset import do_sync
from .hub import generate_hub
from .topology import cmd_topology

# Channels for publishing skills in the project (skills only; memory/graph — separately).
SKILLS_CHANNELS = ("connect", "vendor", "skip")

# Bundle = pre-answers to the checklist. custom → ask interactively.
# mcp=True → distribute dev-default MCP-servers (resolve by autodetect in _gather).
BUNDLES = {
    "minimal":     {"skills": "connect", "perms": False, "mcp": False,
                    "autoapprove": None, "memory": None, "hub": False, "brain": False,
                    "output_style": "lean", "plans_dir": True},
    "recommended": {"skills": "connect", "perms": True, "mcp": True,
                    "autoapprove": "bypass", "memory": None, "hub": True, "brain": False,
                    "output_style": "lean", "plans_dir": True},
    "full":        {"skills": "connect", "perms": True, "mcp": True,
                    "autoapprove": "bypass", "memory": "federation", "hub": True, "brain": True,
                    "output_style": "lean", "plans_dir": True},
}
AA_MODES = ("strict", "permissive", "bypass", "off")
MEM_MODES = ("file", "federation", "agentmemory", "off")
# MCP-servers distributed to development environments by default (presets - in the environment tool).
DEV_MCP = ("context7",)


# --- prompt helpers -----------------------------------------------------------
def _interactive():
    return sys.stdin.isatty()


def _yn(prompt, default):
    suffix = "[Y/n]" if default else "[y/N]"
    ans = input(f"{prompt} {suffix} ").strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes", "d", "yes")


def _ask_yn(prompt, default, interactive):
    return _yn(prompt, default) if interactive else default


def _ask_choice(prompt, options, default, interactive):
    if not interactive:
        return default
    opts = "/".join(o if o != default else o.upper() for o in options)
    while True:
        ans = input(f"{prompt} ({opts}) [{default}]: ").strip().lower()
        if not ans:
            return default
        if ans in options:
            return ans
        print(f"  select from: {', '.join(options)}")


def _ask_text(prompt, default, interactive):
    if not interactive:
        return default
    return input(f"{prompt} [{default}]: ").strip() or default


# --- environment delegation (host command `environment`) -------------------------
def _run_environment(env, args):
    """Execute a host environment-tool command. False — if it is not configured or
    not installed (then the block is skipped softly, as before in the absence of a script)."""
    argv = host_command(env, "environment")
    if argv is None:
        warn("  environment command not configured or not installed - skip"
             + host_install_suffix(env, "environment"))
        return False
    sys.stdout.flush()
    try:
        r = subprocess.run([*argv, *args], check=False, timeout=30,
                           stderr=subprocess.PIPE, text=True)
    except subprocess.TimeoutExpired:
        warn(f"  environment command: timeout exceeded 30s — block may not have been applied "
             f"({args[0] if args else ''})")
        return True
    if r.returncode != 0:
        # graceful: we don’t disable the wizard, but we DO NOT remain silent - otherwise «ready» when not applicable. block
        detail = f": {r.stderr.strip()}" if r.stderr else ""
        warn(f"  environment command returned the code {r.returncode} — block may not have been applied "
             f"({args[0] if args else ''}){detail}")
    return True


# --- choices helpers (selection policy - on the wizard side) --------------------
def _default_mcp(target):
    """MCP-default servers for the development environment (not for obsidian-vault)."""
    return list(DEV_MCP) if autodetect(target) != "obsidian-vault" else []


def _available_mcp(env):
    """Names of available MCP-presets - via `<environment> mcp --list` (empty without it)."""
    argv = host_command(env, "environment")
    if argv is None:
        return []
    try:
        out = subprocess.run([*argv, "mcp", "--list"],
                             capture_output=True, text=True, check=False).stdout
    except OSError:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _parse_mcp_flag(opts):
    """--mcp a,b,c → ['a','b','c'] (trim, without empty)."""
    raw = opts.get("mcp")
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else []


def _add_unique(lst, names):
    """Add names in lst, keeping order and without duplicates. Returns lst."""
    for name in names:
        if name and name not in lst:
            lst.append(name)
    return lst


# --- blocks -------------------------------------------------------------------
def _block_prereqs(env, dry, interactive):
    print("\n[0] Prerequisites (machine-level, one-time)")
    topo = env.home / ".swissknifeman" / "topology.json"
    if topo.exists():
        print("  ✓ topology configured")
    else:
        print("  ✗ no ~/.swissknifeman/topology.json — coordinator and memory without "
              "it is resolved by nodes based on weak defaults")
        if not dry and interactive and _yn("  Run topology init now?", False):
            cmd_topology(env, ["init"])
    hooks = env.home / ".claude" / "hooks"
    have = all((hooks / d).exists() for d in ("notify", "auto-approve", "memory"))
    if have:
        print("  ✓ hook files installed (~/.claude/hooks/)")
    else:
        hint = host_command_text(env, "environment", "hooks", "--global")
        print("  ✗ hook files are not installed"
              + (f" - you need: {hint}" if hint else " - no environment command configured"))
        if not dry and interactive and \
                _yn("  Install hook files globally now?", False):
            _run_environment(env, ["hooks", "--global"])


def _resolve_channel(opts, default, interactive):
    """Skills publication channel: --skills-channel > interactive question > default.
    Returns 'connect'/'vendor' or None (skip)."""
    flag = opts.get("skills_channel")
    if flag:
        if flag not in SKILLS_CHANNELS:
            die(f"--skills-channel: {flag} (valid: connect|vendor|skip)")
        return None if flag == "skip" else flag
    if interactive:
        ch = _ask_choice(
            "Skills publication channel "
            "(connect=plugins, not in repo · vendor=physical copy in repo)",
            SKILLS_CHANNELS, default or "connect", interactive)
        return None if ch == "skip" else ch
    return default


def _block_skills(env, target, choices, dry):
    ch = choices["skills"]
    agent = choices.get("skills_agent") or "claude"
    print(f"\n[1] Skills: {ch or 'pass'}"
          + (f" (agent={agent})" if ch == "vendor" else ""))
    if not ch:
        return
    opts = {"dry_run": dry, "hub": choices["hub"],
            "profile": choices.get("profile") or ""}
    if ch == "connect":
        do_connect(env, target, opts)
    elif ch == "vendor":
        if agent == "claude":
            # modern channel: physical. copies in .claude/skills/ via sync (for
            # external developers without registry access swissknifeman)
            do_sync(env, target, opts)
        else:
            # legacy vendor for Cursor/Gemini (.ai/.cursor)
            opts["agent"] = agent
            do_vendor(env, target, opts)


def _block_perms(env, target, choices, dry):
    if not choices["perms"]:
        print("\n[2] Permissions: pass")
        return
    print("\n[2] Permissions")
    apply_permissions(env, target, choices.get("perms_presets", ""), dry)


def _block_mcp(env, target, choices, dry):
    """Delegate installation MCP-servers to the environment tool (merge-only in .mcp.json)."""
    servers = choices.get("mcp") or []
    print(f"\n[3] MCP-servers: {', '.join(servers) if servers else 'pass'}")
    if not servers:
        return
    args = ["mcp", "--target", str(target), "--mcp", ",".join(servers)]
    if dry:
        args.append("--dry-run")
    _run_environment(env, args)


def _block_autoapprove(env, target, choices, dry):
    mode = choices["autoapprove"]
    print(f"\n[4] auto-approve: {mode or 'pass'}")
    if not mode:
        return
    args = ["hooks", "--target", str(target), "--auto-approve", mode,
            "--file", choices["settings_file"]]
    if dry:
        args.append("--dry-run")
    _run_environment(env, args)


def _block_memory(env, target, choices, dry):
    brain_mode = choices["memory"]
    print(f"\n[5] memory: {('brain=' + choices.get('memory_brain', 'core') + ' mode=' + brain_mode) if brain_mode else 'pass'}")
    if not brain_mode:
        return
    brain = choices.get("memory_brain") or "core"
    args = ["hooks", "--target", str(target), "--memory", f"{brain}:{brain_mode}"]
    if dry:
        args.append("--dry-run")
    _run_environment(env, args)


def _block_output_style(env, target, choices, dry):
    """Terse agent's voice (environment output-style lean) — token-save output. off/None → pass."""
    style = choices.get("output_style")
    print(f"\n[6] output-style: {style or 'pass'}")
    if not style:
        return
    args = ["hooks", "--target", str(target), "--output-style", style]
    if dry:
        args.append("--dry-run")
    _run_environment(env, args)


def _block_plans_dir(env, target, choices, dry):
    """Per-project plans/ (environment hooks --plans-dir plans) — plansDirectory in
    .claude/settings.json (shared, committed), default «yes»: new onboardings are received
    plans/ immediately. Answer «no» = don't call the tool at all - DO NOT call with off (its off
    removes only YOUR default plans, is a different semantics, not «do not install»)."""
    want = choices.get("plans_dir")
    print(f"\n[7] plans-dir: {'plans' if want else 'pass'}")
    if not want:
        return
    args = ["hooks", "--target", str(target), "--plans-dir", "plans"]
    if dry:
        args.append("--dry-run")
    _run_environment(env, args)


def _block_hub(env, target, choices, dry):
    # The hub is already generated internally connect/vendor, if skills+hub. Otherwise - separately.
    if not choices["hub"] or choices["skills"]:
        return
    print("\n[8] Hub")
    if dry:
        print("  [dry-run] would generate a hub (CLAUDE.md / .ai)")
        return
    try:
        generate_hub(env, target)
    except Exception as e:  # noqa: BLE001 — the hub should not crash the wizard
        print(f"  hub pass: {e}")


def _block_brain(env, target, choices, dry):
    if not choices["brain"]:
        return
    print("\n[9] Brain docs-sync")
    # Volt's hint (as before) — notes sync is configured there.
    print("  In the project note in Brain-volte add to frontmatter:")
    print(f"      repo: {target}")
    print("  Then: brain status <project> / brain sync <project>")

    # Doc-sync belongs to the host's brain tool (host command `brain_docs`); it reads the project's
    # configuration itself, so the wizard only hands over the project and the dry-run flag.
    argv = host_command(env, "brain_docs")
    if argv is None:
        warn("  brain command not configured or not installed - skip"
             + host_install_suffix(env, "brain_docs"))
        return
    sys.stdout.flush()
    try:
        r = subprocess.run([*argv, "--project", str(target), *(["--dry-run"] if dry else [])],
                           check=False, timeout=60, stderr=subprocess.PIPE, text=True)
    except subprocess.TimeoutExpired:
        warn("  brain command: timeout exceeded 60s — doc-sync may not have been applied")
        return
    if r.returncode != 0:
        detail = f": {r.stderr.strip()}" if r.stderr else ""
        warn(f"  brain command returned the code {r.returncode} — doc-sync may not have been applied{detail}")


# --- choices assembly ---------------------------------------------------------
def _profile_dict(env, target, opts):
    """Full project profile (by hierarchy flag>config>autodetect) or {} — if
    selection is made explicit buckets/profile does not resolve."""
    config = load_config(env, target)
    name = resolve_profile_name(target, config, opts.get("profile") or "")
    if not name:
        return "", {}
    try:
        return name, load_profile(env, name)
    except SystemExit:
        return name, {}


def _apply_profile_env(base, profile):
    """Infuse the profile CONTENT of the environment into choices: harness_presets/mcp/hooks.
    Bundle sets toggle switches (on/off The), profile populates the values for the type."""
    presets = profile.get("harness_presets")
    if presets:
        base["perms_presets"] = ",".join(presets)
    base["mcp"] = _add_unique(list(profile.get("mcp") or []), base.get("mcp") or [])
    hooks = profile.get("hooks") or {}
    if "auto_approve" in hooks:
        aa = hooks["auto_approve"]
        base["autoapprove"] = None if aa in (None, "off") else aa
    if "memory" in hooks:
        mem = hooks["memory"]
        base["memory"] = None if mem in (None, "off") else mem


def _gather(env, target, opts, bundle, interactive):
    base = dict(BUNDLES.get(bundle, BUNDLES["recommended"]))
    base["settings_file"] = opts.get("file") or "settings.json"
    base["memory_brain"] = "core"
    prof_name, profile = _profile_dict(env, target, opts)
    base["profile"] = prof_name
    if bundle != "custom":
        # auto-presets permissions (autodetect inside the permissions command when empty)
        base["perms_presets"] = ""
        # Skills publication channel: --skills-channel > question (TTY) > bundle default.
        base["skills"] = _resolve_channel(opts, base["skills"], interactive)
        base.setdefault("skills_agent", "claude")
        # mcp=True in the bundle → dev-defaults (context7), but not for obsidian-vault;
        # --mcp <a,b> adds opt-in presets on top (explicit choice hits dev-gate)
        base["mcp"] = _add_unique(
            _default_mcp(target) if base.get("mcp") else [], _parse_mcp_flag(opts))
        # profile (if available) fills presets/mcp/hooks content under type
        _apply_profile_env(base, profile)
        return base

    # custom — interactive checklist
    detected = autodetect(target)
    print(f"Project: {target}  (autodetect: {detected})")
    # Type not recognized → DO NOT set «everything» silently: we suggest choosing a profile explicitly.
    # The user can leave standalone (= put everything) — but this is a conscious choice.
    if detected == "standalone" and interactive and not opts.get("profile"):
        names = sorted(p.stem for p in (env.root / "profiles").glob("*.json"))
        print("  The project type is not recognized. Choose a profile for the optimal set\n"
              "  (or standalone = put everything):")
        prof_name = _ask_choice("  profile", tuple(names), "standalone", interactive)
    ch = {"settings_file": opts.get("file") or "settings.json",
          "memory_brain": "core", "profile": prof_name}
    ch["skills"] = _resolve_channel(opts, "connect", interactive)
    ch["skills_agent"] = "claude"
    if ch["skills"] == "vendor":
        # claude → physical. copies in .claude/skills/ via sync (in the repo);
        # cursor/generic → legacy vendor in .ai/.cursor
        ch["skills_agent"] = _ask_choice(
            "  where (claude=.claude/skills via sync · cursor/generic=.ai/.cursor)",
            ("claude", "cursor", "generic"), "claude", interactive)
    ch["perms"] = _ask_yn("Apply permissions-presets (autodetect)?", True, interactive)
    ch["perms_presets"] = ""
    if detected != "obsidian-vault":
        want_mcp = _ask_yn(
            "Install MCP context7 (up-to-date docs libraries)?", True, interactive)
        ch["mcp"] = list(DEV_MCP) if want_mcp else []
    else:
        ch["mcp"] = []
    # add. opt-in presets: interactive input + flag --mcp
    extra_avail = [m for m in _available_mcp(env) if m not in ch["mcp"]]
    if interactive and extra_avail:
        picked = _ask_text(
            f"  add. MCP-presets separated by commas ({', '.join(extra_avail)}); Enter — pass",
            "", interactive)
        _add_unique(ch["mcp"], (s.strip() for s in picked.split(",")))
    _add_unique(ch["mcp"], _parse_mcp_flag(opts))
    ch["autoapprove"] = _ask_choice("auto-approve mode", AA_MODES + ("skip",),
                                    "bypass", interactive)
    if ch["autoapprove"] == "skip":
        ch["autoapprove"] = None
    join_mem = _ask_yn("Attach the project to the general brain (memory)?", False, interactive)
    if join_mem:
        ch["memory_brain"] = _ask_text("  brain", "core", interactive)
        ch["memory"] = _ask_choice("  mode", MEM_MODES, "federation", interactive)
    else:
        ch["memory"] = None
    ch["output_style"] = "lean" if _ask_yn(
        "Enable terce agent voice (output-style lean — token saving)?",
        True, interactive) else None
    ch["plans_dir"] = _ask_yn(
        "Enable per-project plans/ (plansDirectory — plans Claude Code in the project)?",
        True, interactive)
    ch["hub"] = _ask_yn("Generate skill hub (CLAUDE.md / .ai)?", True, interactive)
    ch["brain"] = _ask_yn("Show tooltip brain docs-sync?", True, interactive)
    return ch


def cmd_integrate(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--dry-run": "bool", "--yes": "bool",
        "--bundle": "str", "--file": "str", "--mcp": "str", "--profile": "str",
        "--skills-channel": "str",
    })
    if opts["help"]:
        print("skiller integrate [--target P] [--bundle minimal|recommended|full|custom] "
              "[--profile name] [--skills-channel connect|vendor|skip] [--yes] [--dry-run] "
              "[--file settings.json|settings.local.json] [--mcp name1,name2]\n"
              "  --skills-channel: connect=plugins (not in repo) · "
              "vendor=physical copy in .claude/skills (in the repo, for external developers)")
        return
    target, _ = resolve_target(env, opts, allow_home_confirm=True)
    if target == env.root.resolve():
        die("is the registry itself swissknifeman — run integrate from the consuming project")
    load_config(env, target)  # early validation .swissknife.json

    dry = opts["dry_run"]
    auto = opts["yes"] or not sys.stdin.isatty()
    bundle = opts["bundle"] or ("recommended" if auto else "custom")
    if bundle not in tuple(BUNDLES) + ("custom",):
        die(f"unknown bundle: {bundle} (minimal|recommended|full|custom)")
    interactive = sys.stdin.isatty() and not opts["yes"]

    print(f"=== skiller integrate → {target} ===")
    print(f"Bundle: {bundle}" + ("  (dry-run — I don't write anything)" if dry else ""))
    choices = _gather(env, target, opts, bundle, interactive)

    _block_prereqs(env, dry, interactive)
    _block_skills(env, target, choices, dry)
    _block_perms(env, target, choices, dry)
    _block_mcp(env, target, choices, dry)
    _block_autoapprove(env, target, choices, dry)
    _block_memory(env, target, choices, dry)
    _block_output_style(env, target, choices, dry)
    _block_plans_dir(env, target, choices, dry)
    _block_hub(env, target, choices, dry)
    _block_brain(env, target, choices, dry)

    print("\n=== Done ===" + (" (dry-run)" if dry else ""))
    print("Restart the session Claude Code in the project so that hooks/plugins picked up.")
