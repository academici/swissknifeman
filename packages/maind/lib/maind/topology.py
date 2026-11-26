"""topology — global local environment map (<state>/maind/topology.json).

Three hub nodes: brain (docs-hub), swissknifeman (skills-hub), projects_base
(workspace). The file is machine-specific and is NOT committed to projects. The legacy
~/.swissknifeman/topology.json is read (one warning) until the new file exists. The
local-topology skill explains the schema and reads it through `maind topology show --json`.

Subcommands:
  init   interactively collect the config (auto-detect defaults, prompt for each node)
  show   print topology (human readable or --json)
"""
import json
import os
import sys

from aicore.state import backup
from aicore.util.cli import parse_flags
from aicore.util.io import atomic_write_json
from aicore.util.repo import find_repo_root
from aicore.util.term import die, now_iso, warn

from .config import Config
from .projects import brain_path

TOPOLOGY_VERSION = 1

# The roles of the nodes are fixed - the config describes WHERE they are, not WHAT they are.
ROLES = {
    "brain": "docs-hub",
    "swissknifeman": "skills-hub",
    "projects_base": "workspace",
}


# --- I/O ----------------------------------------------------------------------
def load_topology(env, quiet=False):
    """Read topology.json. None — if there is no file/it's broken."""
    f = env.topology_file
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        if not quiet:
            warn(f"{f} damaged (invalid JSON) — recreate: "
                 "maind topology init")
        return None
    if data.get("version", 1) > TOPOLOGY_VERSION:
        die(f"{f} is overwritten by a newer version swissknifeman — update the registry "
            "(git pull) and restart install.sh")
    return data


def save_topology(env, data):
    """Atomic record into the active file, after a backup of the existing one."""
    f = env.topology_file
    f.parent.mkdir(parents=True, exist_ok=True)
    backup(f, home=env.home)
    atomic_write_json(f, data)


# --- detection ----------------------------------------------------------------
def detect_projects_base(env):
    """Common ancestor of the fleet projects' local paths; otherwise default ~/projects."""
    try:
        paths = [os.path.expanduser(p["local_path"])
                 for p in Config.load(env).projects if p.get("local_path")]
        if len(paths) >= 2:
            common = os.path.commonpath(paths)
            if common and common != os.sep:
                return common
    except (OSError, ValueError):
        pass
    return str(env.home / "projects")


def detect_brain(env):
    """The vault the node knows about, else the conventional ~/Vaults/Brain."""
    try:
        found = brain_path(Config.load(env))
    except (OSError, ValueError):
        found = None
    return found or str(env.home / "Vaults" / "Brain")


def _norm(path):
    path = (path or "").strip()
    return os.path.abspath(os.path.expanduser(path)) if path else ""


def _build(nodes):
    return {key: {"path": _norm(nodes.get(key, "")), "role": role}
            for key, role in ROLES.items()}


# --- subcommands --------------------------------------------------------------
def _prompt(label, default, interactive):
    if not interactive:
        return default
    suffix = f" [{default}]" if default else ""
    return input(f"{label}{suffix}: ").strip() or default


def _show_data(data):
    print(f"Topology (version {data.get('version', '?')}):")
    for key, node in data.get("nodes", {}).items():
        print(f"  {key:14}{node.get('path', '')}  ({node.get('role', '')})")


def _cmd_show(env, as_json):
    data = load_topology(env)
    if data is None:
        if as_json:
            print(json.dumps({"version": TOPOLOGY_VERSION, "nodes": {}}))
        else:
            print("The topology is not configured. Create: maind topology init")
        return
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        _show_data(data)


def _cmd_init(env, opts):
    existing = load_topology(env, quiet=True) or {}
    prev = existing.get("nodes", {})

    def default_for(key, flag, detect):
        return (opts.get(flag) or prev.get(key, {}).get("path")
                or detect)

    brain = default_for("brain", "brain", detect_brain(env))
    skman = default_for("swissknifeman", "swissknifeman",
                        str(find_repo_root(env.root) or env.root))
    base = default_for("projects_base", "projects_base", detect_projects_base(env))

    interactive = sys.stdin.isatty() and not opts.get("yes")
    if interactive:
        print("Topology setup (Enter — leave default value):")
    brain = _prompt("  Brain-volt (docs-hub)", brain, interactive)
    skman = _prompt("  swissknifeman (skills-hub)", skman, interactive)
    base = _prompt("  project database (workspace)", base, interactive)

    data = {
        "version": TOPOLOGY_VERSION,
        "nodes": _build({"brain": brain, "swissknifeman": skman,
                         "projects_base": base}),
        "created_at": existing.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    save_topology(env, data)
    print(f"Recorded: {env.topology_file}")
    _show_data(data)


def cmd_topology(env, argv):
    argv = list(argv)
    sub = argv.pop(0) if argv and not argv[0].startswith("-") else "show"
    opts = parse_flags(argv, {
        "--json": "bool", "--brain": "str", "--swissknifeman": "str",
        "--projects-base": "str", "--yes": "bool",
    })
    if opts["help"]:
        print("maind topology <init|show> [--json] [--brain PATH] "
              "[--swissknifeman PATH] [--projects-base PATH] [--yes]")
        return
    if sub == "init":
        _cmd_init(env, opts)
    elif sub == "show":
        _cmd_show(env, as_json=opts["json"])
    else:
        die(f"unknown subcommand topology: {sub} (pending init|show)")
