"""Single trust space Claude Code, controlled from the hub maind (hub-scoped).

Problem: when editing adjacent projects Claude Code specifies a request «trust the directory?»
(workspace boundary). This is SEPARATE from allow/deny system - bypassPermissions
does NOT jam it. Fix - add paths of all ecosystem projects to
permissions.additionalDirectories settings.

The module generates/accompanies .claude/settings.local.json AT THE ROOT maind: trust
gets session Claude, launched from the hub. Project register (.maind.json) — the only one
source of truth. The record is idempotent and ADDITIVE: other people's records and user-specified
defaultMode do not touch. Mirror mcpconfig.py (load → merge → write) for settings Claude."""
import copy
import json
import os
from pathlib import Path

from aicore.util.io import atomic_write_json
from aicore.util.partners import PartnerUnavailable
from aicore.util.term import die, warn
from .. import harness_link
from aicore.util.cli import parse_args
from ..common import save_backup
from ..config import load_config

DEFAULT_MODE = "acceptEdits"


def hub_settings_path(env):
    """Where do they live? hub-trust settings (gitignored, absolute personal paths)."""
    return env.root / ".claude" / "settings.local.json"


def norm_path(p):
    """Path normalization for comparison/grandfather: expanduser + realpath (resolves symlinks and
    `.`/`..`-segments). N4: used to be only normpath — repeated `maind onboard` via
    symlink/another equivalent path to the same directory stamped a duplicate project record
    (_ensure_project match according to normalized local_path). realpath is also safe for
    non-existent paths (resolves the existing prefix, leaves the rest as is)."""
    return os.path.realpath(os.path.expanduser(str(p)))


def load_settings(path):
    """(data, existed). No file → ({}, False). Broken JSON → die (DO NOT touch someone else's file)."""
    path = Path(path)
    if not path.exists():
        return {}, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path}: broken JSON settings Claude — I don't touch it, fix it manually: {e}")
    if not isinstance(data, dict):
        die(f"{path}: settings object expected Claude")
    return data, True


def eligible_paths(config):
    """Sorted unique list of absolute paths of included projects whose
    directory exists on disk. Without local_path / disabled / missing path - skipping."""
    seen = set()
    for p in config.get("projects") or []:
        if p.get("enabled") is False:
            continue
        lp = p.get("local_path")
        if not lp:
            continue
        norm = norm_path(lp)
        if Path(norm).is_dir():
            seen.add(norm)
    return sorted(seen)


def build_fragment(paths, *, allow=True, mode=True):
    """Settings fragment Claude for trusted directories.

    additionalDirectories repairs the workspace boundary; allow (Read/Edit-globs)
    and defaultMode additionally remove friction even without bypass. Absolute path in
    permission-rule - with double slash: Read(//abs/path/**)."""
    perms = {"additionalDirectories": list(paths)}
    if allow:
        rules = []
        for p in paths:
            rules.append(f"Read(/{p}/**)")
            rules.append(f"Edit(/{p}/**)")
        perms["allow"] = rules
    if mode:
        perms["defaultMode"] = DEFAULT_MODE
    return {"permissions": perms}


def merge_settings(existing, fragment):
    """Drains fragment in existing idempotent/additive. Returns (merged, changed).

    Lists (additionalDirectories, allow) — union with dedup, order of existing and
    other people's records are saved. defaultMode is set ONLY if it is not already set (not
    override user selection). Any extraneous settings keys are retained."""
    merged = copy.deepcopy(existing) if existing else {}
    changed = False
    perms = merged.get("permissions")
    if not isinstance(perms, dict):
        perms = {}
        merged["permissions"] = perms
    fperms = fragment.get("permissions") or {}

    for key in ("additionalDirectories", "allow"):
        incoming = fperms.get(key)
        if not incoming:
            continue
        cur = perms.get(key)
        cur = list(cur) if isinstance(cur, list) else []
        have = set(cur)
        for item in incoming:
            if item not in have:
                cur.append(item)
                have.add(item)
                changed = True
        perms[key] = cur

    if "defaultMode" in fperms and "defaultMode" not in perms:
        perms["defaultMode"] = fperms["defaultMode"]
        changed = True

    return merged, changed


def sync(env, config, *, allow=True, mode=True, dry=False, backup=True):
    """Write/update hub-trust settings from the project registry. Returns metadata.
    dry=True — does not write anything (will return the intended merged in result['settings'])."""
    path = hub_settings_path(env)
    existing, _existed = load_settings(path)
    paths = eligible_paths(config)
    fragment = build_fragment(paths, allow=allow, mode=mode)

    before = existing.get("permissions") or {}
    before_dirs = set(before.get("additionalDirectories") or [])
    before_allow = set(before.get("allow") or [])
    had_mode = "defaultMode" in before

    merged, changed = merge_settings(existing, fragment)
    after = merged.get("permissions") or {}
    result = {
        "path": str(path),
        "total_paths": len(paths),
        "dirs_added": sorted(set(after.get("additionalDirectories") or []) - before_dirs),
        "allow_added": len(set(after.get("allow") or []) - before_allow),
        "mode_set": (not had_mode) and ("defaultMode" in after),
        "changed": changed,
        "dry": dry,
        "settings": merged,
    }
    if not dry and changed:
        if backup:
            save_backup(path, project=env.root)
        atomic_write_json(path, merged)
    return result


def trusted_dirs(env):
    """Set of trusted directories from hub-settings (normalized). No/broken → is empty."""
    path = hub_settings_path(env)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    dirs = (data.get("permissions") or {}).get("additionalDirectories") or []
    return {norm_path(d) for d in dirs}


def provider_trust(context, *, trusted, profile_id="workspace-contained",
                   operation_id=None, target_identity=None, origin="operation"):
    """Evaluate P5 trust/security per already-resolved effective provider, no writes."""
    rows = []
    for provider in context.provider_context.effective_providers:
        try:
            resolution = harness_link.resolve_profile(
                provider.provider_id.value, profile_id, target_scope="project", trusted=trusted,
                operation_id=operation_id, target_identity=target_identity, origin=origin,
                enabled=provider.enabled)
        except PartnerUnavailable as error:
            # Trust cannot be established without harness: the provider stays non-green.
            warn(str(error))
            rows.append({"provider_id": provider.provider_id.value, "green": False,
                         "diagnostics": ["PARTNER_UNAVAILABLE"]})
            continue
        rows.append({"provider_id": provider.provider_id.value, "green": resolution["green"],
                     "diagnostics": [item["code"] for item in resolution["diagnostics"]]})
    return tuple(rows)


def audit(env, config):
    """Read-only registry diff and hub-settings: covered / missing / drift."""
    trusted = trusted_dirs(env)
    registry = {}  # norm_path → project id
    for p in config.get("projects") or []:
        lp = p.get("local_path")
        if lp:
            registry[norm_path(lp)] = p.get("id")
    reg = set(registry)
    return {
        "settings": str(hub_settings_path(env)),
        "trusted_count": len(trusted),
        "registry_count": len(reg),
        "covered": [{"id": registry[p], "path": p} for p in sorted(reg & trusted)],
        "missing": [{"id": registry[p], "path": p} for p in sorted(reg - trusted)],
        "drift": sorted(trusted - reg),  # trusted, but not from the registry
    }


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_workspace(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind workspace <sync|status> "
              "[--dry-run] [--no-allow] [--no-mode] [--json]")
        return
    sub, rest = argv[0], argv[1:]
    if sub == "sync":
        _cmd_sync(env, rest)
    elif sub == "status":
        _cmd_status(env, rest)
    else:
        die(f"unknown subcommand workspace: {sub} (sync|status)")


def _cmd_sync(env, argv):
    opts, _ = parse_args(argv, {"--dry-run": "bool", "--no-allow": "bool",
                                "--no-mode": "bool", "--json": "bool"})
    config, _src = load_config(env)
    result = sync(env, config, allow=not opts["no_allow"],
                  mode=not opts["no_mode"], dry=opts["dry_run"])
    if opts["json"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    tag = "[dry-run] " if result["dry"] else ""
    if result["changed"]:
        extra = f", allow +{result['allow_added']}" if result["allow_added"] else ""
        extra += f", defaultMode={DEFAULT_MODE}" if result["mode_set"] else ""
        print(f"{tag}Trust → {result['path']}")
        print(f"  directories: {result['total_paths']} "
              f"(added {len(result['dirs_added'])}){extra}")
    else:
        print(f"{tag}Trust is already relevant ({result['total_paths']} directories) "
              f"→ {result['path']}")
    if result["dry"] and result["changed"]:
        print(json.dumps(result["settings"], ensure_ascii=False, indent=2))


def _cmd_status(env, argv):
    opts, _ = parse_args(argv, {"--json": "bool"})
    config, _src = load_config(env)
    a = audit(env, config)
    if opts["json"]:
        print(json.dumps(a, ensure_ascii=False, indent=2))
        return
    print(f"Trust Claude (hub): {a['settings']}")
    print(f"  trusted {len(a['covered'])}/{a['registry_count']} registry projects")
    for m in a["missing"]:
        print(f"  ✗ not trusted: {m['id']} ({m['path']})")
    for d in a["drift"]:
        print(f"  ? extra directory (not from the registry): {d}")
