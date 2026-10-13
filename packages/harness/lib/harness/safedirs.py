"""Internal documentation."""
import importlib.util
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from aicore.state import config_dir, state_dir
from aicore.util.cli import parse_args
from aicore.util.io import safe_load_json
from aicore.util.repo import find_monorepo_root
from aicore.util.term import die, warn
from .settings import load_settings, remove_permission_rules, write_json

SUBCOMMANDS = ("init", "list", "add", "remove", "prune-ask", "delete")



PRUNE_ASK_RULES = ("Bash(rm -r *)", "Bash(rm -rf *)")

DEFAULT_CONFIG = {
    "version": 1,
    "include_registered_projects": True,
    "dirs": [],
    "exclude": [],
    "protect_git": True,
    "allow_globs": True,
}


def _registry_file(home, owner, name):
    """The registry file of another module: its own state file (``<state>/<owner>/<name>``), else the legacy
    ``~/.swissknifeman/<name>`` while only that one exists (never under ``SKM_HOME``, which switches legacy lookups off)."""
    new = state_dir(owner, home=home) / name
    legacy = Path(home) / ".swissknifeman" / name
    if new.exists() or os.environ.get("SKM_HOME") or not legacy.exists():
        return new
    return legacy


def new_state_file(env):
    """`<config>/harness/safe-dirs.json` (`SKM_HOME` isolates it; a relative `SKM_HOME` is ignored)."""
    environ = dict(os.environ)
    try:
        base = config_dir(env=environ, home=env.home)
    except ValueError:
        environ.pop("SKM_HOME", None)
        base = config_dir(env=environ, home=env.home)
    return base / "harness" / "safe-dirs.json"


def state_candidates(env):
    """The ladder, nearest first. Identical to the one in the auto-approve hook (parity test)."""
    override = os.environ.get("SKM_SAFE_DIRS_CONFIG")
    if override:
        return [Path(override)]
    found = [new_state_file(env)]
    root = find_monorepo_root(env.root)  # legacy rung until values move to the new place
    if root:
        found.append(root / "safe-dirs.json")
    found.append(_legacy_file(env))
    return found


def _state_file(env):
    """The first existing file of the ladder; the new place when none exists."""
    candidates = state_candidates(env)
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def _legacy_file(env):
    return env.home / ".swissknifeman" / "safe-dirs.json"


def _hook_module(env):
    """Internal documentation."""
    path = (env.configs_dir / "hooks" / "auto-approve" / "lib" / "safedirs.py")
    spec = importlib.util.spec_from_file_location("hook_safedirs", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_config(env):
    f = _state_file(env)
    if not f.exists():
        die(f"no {f} — first: harness safe-dirs init")
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{f}: invalid JSON: {e}")
    if not isinstance(cfg, dict) or cfg.get("version") != 1:
        die(f"{f}: unknown format (version != 1)")
    return cfg, f


def _validate_root(env, raw):
    """Internal documentation."""
    mod = _hook_module(env)
    home = str(env.home)
    resolved = mod._norm_root(raw, home, str(Path(home).resolve()))
    if resolved is None:
        die(f"invalid root: {raw!r} — needs absolute (or ~/) path, "
            "not '/', not $HOME and not an ancestor $HOME")
    return resolved


def cmd_init(env, opts):
    f = _state_file(env)
    if f.exists():
        print(f"already exists: {f}")
        return
    write_json(f, DEFAULT_CONFIG, opts["dry_run"])
    print("  default: include_registered_projects=true (the skiller project registry, "
          "<state>/skiller/projects.json); explicit roots - harness safe-dirs add <path>")
    print(f"  sample roots: {env.root / 'configs' / 'safe-dirs.example.json'}")


def cmd_list(env, _opts):
    cfg, f = _load_config(env)
    mod = _hook_module(env)
    allow = mod.load_allowlist(str(env.home), str(f))
    print(f"config: {f}")
    if allow is None:
        warn("the config is not loaded by the eyes of the hook - the feature is DISABLED (rm is blocked as before)")
        return
    print(f"  include_registered_projects={cfg.get('include_registered_projects')}, "
          f"protect_git={allow['protect_git']}, allow_globs={allow['allow_globs']}")
    print(f"effective roots ({len(allow['roots'])}):")
    for r in allow["roots"]:
        print(f"  {r}")
    if not allow["roots"]:
        print("  (empty — rm is blocked everywhere, add: harness safe-dirs add <path>)")
    if allow["excludes"]:
        print(f"seizures ({len(allow['excludes'])}):")
        for e in allow["excludes"]:
            print(f"  {e}")


def cmd_add(env, opts, raw):
    cfg, f = _load_config(env)
    key = "exclude" if opts["exclude"] else "dirs"
    if key == "dirs":
        resolved = _validate_root(env, raw)
    else:
        mod = _hook_module(env)
        resolved = mod._abs_real(raw, str(env.home))
        if resolved is None:
            die(f"invalid withdrawal: {raw!r} — needs absolute (or ~/) path")
    entries = cfg.setdefault(key, [])
    mod = _hook_module(env)
    existing = [mod._abs_real(x, str(env.home)) for x in entries]
    if resolved in existing:
        print(f"is already in {key}: {raw} ({resolved})")
        return
    entries.append(raw)
    write_json(f, cfg, opts["dry_run"])
    print(f"  added to {key}: {raw} → {resolved}")


def cmd_remove(env, opts, raw):
    cfg, f = _load_config(env)
    key = "exclude" if opts["exclude"] else "dirs"
    mod = _hook_module(env)
    target = mod._abs_real(raw, str(env.home))
    entries = cfg.get(key) or []
    kept = [x for x in entries if mod._abs_real(x, str(env.home)) != target]
    if len(kept) == len(entries):
        die(f"not found in {key}: {raw}")
    cfg[key] = kept
    write_json(f, cfg, opts["dry_run"])
    print(f"  removed from {key}: {raw}")


def _prune_one(target_dir, fname, dry):
    """Internal documentation."""
    f = Path(target_dir) / ".claude" / fname
    if not f.exists():
        return 0
    settings, f = load_settings(Path(target_dir), fname)
    removed = remove_permission_rules(settings, "ask", PRUNE_ASK_RULES)
    if removed:
        write_json(f, settings, dry)
        print(f"  {f}: removed ask-rules rm: {removed}")
    return removed


def cmd_prune_ask(env, opts):
    if not (opts["global"] or opts["target"] or opts["all_projects"]):
        die("needs at least one of: --global / --target P / --all-projects")
    total = 0
    if opts["global"]:
        total += _prune_one(env.home, "settings.json", opts["dry_run"])
    targets = []
    if opts["target"]:
        targets.append(Path(opts["target"]).expanduser())
    if opts["all_projects"]:
        reg = safe_load_json(_registry_file(env.home, "skiller", "projects.json"), {}) or {}
        targets += [Path(p["path"]) for p in reg.get("projects", [])
                    if isinstance(p, dict) and isinstance(p.get("path"), str)]
    for t in targets:
        if not t.is_dir():
            warn(f"pass (no directory): {t}")
            continue
        for fname in ("settings.json", "settings.local.json"):
            total += _prune_one(t, fname, opts["dry_run"])
    print(f"total rules removed: {total}" if total else
          "ask-rules rm not found - pure")


_FORBIDDEN_CHARS = ("$", "`", "{", "}", "*", "?", "[")


def _log_delete(log_file, raw, resolved, result, dry_run):
    """Internal documentation."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw": raw, "resolved": resolved, "result": result, "dry_run": dry_run,
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cmd_delete(env, opts, paths):
    """Internal documentation."""
    if not paths:
        die("needs at least one path: harness safe-dirs delete <path> [<path> …] [--dry-run]")
    cfg, f = _load_config(env)
    mod = _hook_module(env)
    allow = mod.load_allowlist(str(env.home), str(f))
    if allow is None:
        die("config safe-dirs does not load using the hook - first: harness safe-dirs init")
    home = str(env.home)
    log_file = env.home / ".claude" / "logs" / "safe-delete-decisions.jsonl"
    resolved = []
    for raw in paths:
        if any(ch in raw for ch in _FORBIDDEN_CHARS):
            die(f"invalid path (globs/substitutions are prohibited - only "
                f"specific file/folder): {raw!r}")
        if ".." in raw.split("/"):
            die(f"invalid path (component '..'): {raw!r}")
        p = mod._abs_real(raw, home)
        if p is None:
            die(f"path must be absolute (or ~/subpath): {raw!r}")
        if not mod._contained(p, allow, allow_root=False):
            die(f"outside the trusted tree (safe-dirs.json) — failure: {raw!r} → {p}")
        resolved.append((raw, p))
    for raw, p in resolved:
        exists = os.path.lexists(p)
        if not exists:
            print(f"  pass (is no longer available): {raw}")
            _log_delete(log_file, raw, p, "skip-absent", opts["dry_run"])
            continue
        if opts["dry_run"]:
            print(f"  [dry-run] would remove: {raw} → {p}")
            _log_delete(log_file, raw, p, "dry-run", True)
            continue
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        except OSError as e:
            _log_delete(log_file, raw, p, f"error: {e}", False)
            die(f"deletion error {raw} ({p}): {e}")
        print(f"  deleted: {raw} → {p}")
        _log_delete(log_file, raw, p, "deleted", False)


def cmd_safedirs(env, argv):
    opts, pos = parse_args(argv, {
        "--exclude": "bool", "--global": "bool", "--target": "str",
        "--all-projects": "bool", "--dry-run": "bool",
    }, max_pos=64)
    if opts["help"] or not pos:
        print("harness safe-dirs <init|list|add|remove|prune-ask|delete>\n"
              "  init                          create <config>/harness/safe-dirs.json\n"
              "  list                          effective allowlist through the eyes of a hook\n"
              "  add <path> [--exclude]        add root (or withdrawal)\n"
              "  remove <path> [--exclude]     remove root (or withdrawal)\n"
              "  prune-ask [--global] [--target P] [--all-projects]\n"
              "                                remove ask-rules rm from settings\n"
              "  delete <path> [<path> …]      delete directly (escape hatch for\n"
              "                                for/xargs/sudo-blocked rm)\n"
              "General: [--dry-run]")
        return
    sub = pos[0]
    if sub not in SUBCOMMANDS:
        die(f"unknown subcommand: {sub} ({'|'.join(SUBCOMMANDS)})")
    if sub in ("add", "remove"):
        if len(pos) < 2:
            die(f"need path: harness safe-dirs {sub} <path>")
        (cmd_add if sub == "add" else cmd_remove)(env, opts, pos[1])
        return
    if sub == "delete":
        cmd_delete(env, opts, pos[1:])
        return
    if len(pos) > 1:
        die(f"extra argument: {pos[1]}")
    if sub == "init":
        cmd_init(env, opts)
    elif sub == "list":
        cmd_list(env, opts)
    else:
        cmd_prune_ask(env, opts)
