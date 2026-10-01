"""maind run — orchestration: pull internal commands of neighboring packages from one point.

Command post: maind does not rewrite functionality brain/swissknifeman, and delegates to them
by white list of capabilities (CAPABILITIES). Neighbors' launchers find their own root,
so the absolute path to bin + arguments. None shell=True — only argv-list."""
import os
import subprocess
import sys
from pathlib import Path

from ..common import die, parse_args
from ..config import load_config
from ..constants import SIBLINGS
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
    # delivered agents + local skills + /task:*; provider router-config in sync.
    "env:router":    ("harness", ["router", "--generate", "--target", "{path}"], True),
    # deterministic delivery of a pack of subagents (--pack comes to extra):
    # render --auto resolves interviews without an agent; upgrade — version upgrade.
    "env:agent-pack":         ("harness",
                               ["agent-packs", "render", "--auto", "--target", "{path}"], True),
    "env:agent-pack-upgrade": ("harness",
                               ["agent-packs", "upgrade", "--target", "{path}"], True),
}

# SIBLINGS (how to find your neighbor's launcher) — in constants.py (shared with sync, without lazy-import).

# Opportunities whose neighbor launcher supports YOURS `--dry-run` (harness env:*): when dry
# throw the flag and launch for REAL → honest preview (versions/pack conflicts,
# that will actually be recorded), and not print+rc0. For others (doesn't have one dry) — intent seal.
# Reason: `maind sync --dry-run` gave a false green preview of the pack upgrade (field-feedback).
DRY_CAPABLE = {"env:apply", "env:mcp", "env:hooks",
               "env:agent-pack", "env:agent-pack-upgrade", "env:router", "skm:update"}


def _sibling_bin(config, which):
    spec = SIBLINGS[which]
    override = os.environ.get(spec["env"])
    if override:
        p = Path(os.path.expanduser(override))
        if not p.exists():
            die(f"{spec['env']}={override} — file not found")
        return p
    proj = get_project(config, spec["project_id"])
    root = proj.get(spec["path_key"]) if proj else None
    # brain: if there is no project record - resolve vault same as sync (brain_path):
    # integrations.brain.path → vault project brain → default ~/Vaults/Brain. brain_path
    # can return the path to the .projects.json — normalize to directory vault (its parent).
    if not root and which == "brain":
        from ..projects import brain_path
        bp = Path(os.path.expanduser(brain_path(config)))
        root = str(bp.parent if bp.name.endswith(".json") else bp)
    if not root:
        die(f"{which} not found: add project '{spec['project_id']}' with {spec['path_key']} "
            f"in config.json, or set {spec['env']}")
    binp = Path(os.path.expanduser(root)) / spec["bin"]
    if not binp.exists():
        die(f"{which}: launcher not found - {binp}")
    return binp


def run_capability(env, config, project_id, capability, extra=None, *, dry=False):
    """Delegate a capability to a neighboring package. Returns the return code of the child process."""
    if capability not in CAPABILITIES:
        die(f"unknown capability: {capability}\navailable: "
            + ", ".join(sorted(CAPABILITIES)))
    sibling, template, needs_project = CAPABILITIES[capability]
    binp = _sibling_bin(config, sibling)
    subst = {}
    if needs_project:
        proj = get_project(config, project_id)
        if proj is None:
            die(f"project not found in config.json: {project_id}")
        subst = {"project": proj.get("id", project_id),
                 "path": os.path.expanduser(proj.get("local_path") or "")}
    argv = [str(binp)] + [a.format(**subst) for a in template] + list(extra or [])
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
