"""maind run — orchestration: pull internal commands of neighboring packages from one point.

Command post: maind does not rewrite functionality brain/swissknifeman, and delegates to them
by white list of capabilities (CAPABILITIES). Neighbors' launchers find their own root,
so the absolute path to bin + arguments. None shell=True — only argv-list."""
import os
import subprocess
import sys
from pathlib import Path

from aicore.util.cli import parse_args
from aicore.util.partners import PartnerUnavailable, require_partner
from aicore.util.term import die
from ..config import load_config
from ..projects import brain_path
from ..projects import get as get_project

# Whitelist: name → (sibling, argv-template, needs_project). {project}=id, {path}=local_path.
CAPABILITIES = {
    "brain:sync":    ("brain", ["sync", "{project}"], True),
    "brain:status":  ("brain", ["status", "{project}", "--json"], True),
    "brain:list":    ("brain", ["list"], False),
    "skm:vendor":    ("swissknifeman", ["vendor", "--target", "{path}"], True),
    "skm:update":    ("swissknifeman", ["update", "--target", "{path}"], True),
    "skm:lock":      ("swissknifeman", ["lock", "--target", "{path}"], True),
    "skm:integrate": ("swissknifeman", ["integrate", "--target", "{path}"], True),
    "skm:status":    ("swissknifeman", ["status", "--target", "{path}"], True),
    # environment Claude Code (permissions/MCP/hooks) — package harness. skiller integrate
    # is already calling harness under the hood; env:* are needed for direct/granular application
    # environment (e.g. at onboard --skip-skills) and for router'and umbrella `swissknifeman env`.
    # env:apply — permissions; env:mcp/env:hooks — spot rolling MCP-servers/hooks.
    "env:apply":     ("harness", ["permissions", "--target", "{path}"], True),
    "env:mcp":       ("harness", ["mcp", "--target", "{path}"], True),
    "env:hooks":     ("harness", ["hooks", "--target", "{path}"], True),
    # features catalog intent-router (.claude/agent-router.config.json) from
    # delivered agents + local skills + /planner:*; provider router-config in sync.
    "env:router":    ("harness", ["router", "--generate", "--target", "{path}"], True),
    # deterministic delivery of a pack of subagents (--pack comes to extra):
    # render --auto resolves interviews without an agent; upgrade — version upgrade.
    "env:agent-pack":         ("harness",
                               ["agent-packs", "render", "--auto", "--target", "{path}"], True),
    "env:agent-pack-upgrade": ("harness",
                               ["agent-packs", "upgrade", "--target", "{path}"], True),
}

# Opportunities whose neighbor launcher supports YOURS `--dry-run` (harness env:*): when dry
# throw the flag and launch for REAL → honest preview (versions/pack conflicts,
# that will actually be recorded), and not print+rc0. For others (doesn't have one dry) — intent seal.
# Reason: `maind sync --dry-run` gave a false green preview of the pack upgrade (field-feedback).
DRY_CAPABLE = {"env:apply", "env:mcp", "env:hooks",
               "env:agent-pack", "env:agent-pack-upgrade", "env:router", "skm:update"}


# sibling → (partner name, deprecated launcher variable). brain is the external vault CLI:
# it lives inside the vault folder reported by `brain vault --json`, not on PATH.
_PARTNERS = {
    "swissknifeman": ("skiller", ("MAIND_SKM_BIN",)),
    "harness": ("harness", ("MAIND_HARNESS_BIN",)),
}
_BRAIN_LEGACY_BIN = "MAIND_BRAIN_BIN"
_warned = set()


def _unavailable(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _brain_cli(config):
    legacy = os.environ.get(_BRAIN_LEGACY_BIN)
    if legacy:
        path = Path(os.path.expanduser(legacy))
        if not path.exists():
            die(f"{_BRAIN_LEGACY_BIN}={legacy} - file not found")
        if _BRAIN_LEGACY_BIN not in _warned:
            _warned.add(_BRAIN_LEGACY_BIN)
            print(f"{_BRAIN_LEGACY_BIN}_DEPRECATED: {_BRAIN_LEGACY_BIN} is deprecated; "
                  "configure the vault with the brain module", file=sys.stderr)
        return [str(path)]
    vault = brain_path(config)
    if not vault:
        _unavailable("PARTNER_UNAVAILABLE: brain vault not found "
                     "(set SKM_BRAIN_ROOT or put brain on PATH)")
    root = Path(os.path.expanduser(vault))
    root = root.parent if root.name.endswith(".json") else root
    binp = root / "bin" / "brain"
    if not binp.exists():
        die(f"brain: launcher not found - {binp}")
    return [str(binp)]


def _sibling_argv(config, which):
    """Argv prefix of a neighboring package, found through aicore.util.partners.
    A missing partner exits with PARTNER_UNAVAILABLE (callers turn it into a skip)."""
    if which == "brain":
        return _brain_cli(config)
    name, legacy = _PARTNERS[which]
    try:
        return require_partner(name, legacy_env=legacy)
    except PartnerUnavailable as exc:
        _unavailable(str(exc))


def _sibling_bin(config, which):
    return Path(_sibling_argv(config, which)[0])


def run_capability(env, config, project_id, capability, extra=None, *, dry=False):
    """Delegate a capability to a neighboring package. Returns the return code of the child process."""
    if capability not in CAPABILITIES:
        die(f"unknown capability: {capability}\navailable: "
            + ", ".join(sorted(CAPABILITIES)))
    sibling, template, needs_project = CAPABILITIES[capability]
    prefix = _sibling_argv(config, sibling)
    subst = {}
    if needs_project:
        proj = get_project(config, project_id)
        if proj is None:
            die(f"project not found in config.json: {project_id}")
        subst = {"project": proj.get("id", project_id),
                 "path": os.path.expanduser(proj.get("local_path") or "")}
    argv = list(prefix) + [a.format(**subst) for a in template] + list(extra or [])
    if dry:
        if capability in DRY_CAPABLE:
            # neighbor knows how to --dry-run → honest preview (real rc/conflicts), not rc0
            return subprocess.run(argv + ["--dry-run"], check=False).returncode
        print("[dry-run] " + " ".join(argv))
        return 0
    return subprocess.run(argv, check=False).returncode


def list_capabilities():
    for name in sorted(CAPABILITIES):
        sib, tmpl, _ = CAPABILITIES[name]
        print(f"  {name:<16} {sib}: {' '.join(tmpl)}")


def cmd_run(env, argv):
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    opts, pos = parse_args(argv, {"--list": "bool", "--dry-run": "bool"}, max_pos=2)
    if opts["list"] or (pos[:1] == ["list"]):
        list_capabilities()
        return
    if len(pos) < 2:
        die("usage: maind run <project> <capability> [-- additional arguments]\n"
            "list of features: maind run --list")
    config, _src = load_config(env)
    rc = run_capability(env, config, pos[0], pos[1], extra, dry=opts["dry_run"])
    if rc:
        sys.exit(rc)
