"""status — read-only project report."""
import json
import os
import shutil
from pathlib import Path

from core import find_repo_root

from .budget import budget_for_set, listing_measurements, resolve_active_set
from .common import (AGENT_DEFAULTS, MANIFEST, MARKETPLACE, atomic_write_json, die,
                     parse_flags, parse_frontmatter)
from .config import ProjectConfig, find_project_root, load_config, resolve_selection
from .registry import alias_migration_hints, load_bucket_aliases
from .state import db_records, print_registry_state
from .update import detect_marketplace_file, detect_vendor_path

# The hub's memory-tool sync writes these at fixed paths; they share registry names with
# host bootstrap but are NOT skiller-vendored copies (see skilldoc.py).
MAIND_MANAGED_SKILL_NAMES = frozenset({"ecosystem-mcp", "ecosystem-setup"})


def _bucket_of(source_path):
    """Bucket from source_path vendor skill ('skills/<bucket>/<rel>' → bucket)."""
    parts = Path(source_path).parts
    return parts[1] if len(parts) >= 2 and parts[0] == "skills" else None


def channel_overlap(enabled, vendored_buckets):
    """Buckets active AT THE SAME TIME as a plugin (connect) and vendor (vendor) —
    skills of such a bucket are distributed twice. Returns a sorted list."""
    return sorted(set(enabled) & set(vendored_buckets))


def detect_raw_vendor_path(target, config):
    """Vendor channel WITHOUT manifest: skills arrived as symlinks/copies
    from a third party source (`.ai/skills` etc.), not via `skiller sync` — y
    `detect_vendor_path` (needed `.swissknifeman-manifest.json`) such a channel is invisible,
    and `channel_overlap` is silent on it (repo fact `flexcrm`,
    `findings/P3-listing-hygiene-and-vendoring-facts.md` §2.3). Returns the first
    non-empty from the same candidates as `detect_vendor_path`, WITHOUT the manifest requirement."""
    config = ProjectConfig.coerce(config)  # historical calls are sent dict
    candidates = []
    if config.skills_path:
        candidates.append(config.skills_path)
    candidates += [p for p in AGENT_DEFAULTS.values() if p not in candidates]
    for p in candidates:
        d = target / p
        if d.is_dir() and any(d.iterdir()):
            return p
    return None


def local_channel_entries(skills_dir):
    """Local skill catalog entries (symlinks+directories), including the dead.
    -> [{"dir": name, "dead": bool, "name": frontmatter name | None}]. `dead` —
    broken symlink OR directory without `SKILL.md` (P3.5 delta in, repo fact `flexcrm`:
    41 broken symlink of 58 records)."""
    entries = []
    if not skills_dir.is_dir():
        return entries
    for p in sorted(skills_dir.iterdir()):
        if p.name == MANIFEST or p.name.startswith("."):
            continue
        if p.is_symlink() and not p.exists():
            entries.append({"dir": p.name, "dead": True, "name": None})
            continue
        if not p.is_dir():
            continue
        md = p / "SKILL.md"
        if not md.is_file():
            entries.append({"dir": p.name, "dead": True, "name": None})
            continue
        try:
            fm = parse_frontmatter(md)
            name = fm.get("name") or p.name
        except Exception:
            name = p.name
        entries.append({"dir": p.name, "dead": False, "name": name})
    return entries


def registry_skill_names(env):
    """frontmatter `name` -> [buckets], across the ENTIRE registry (not only enabled
    buckets): double is the second physical copy of the registry skill, living outside
    registry and not updated `skiller update`, regardless of whether it is enabled
    today donor bucket (P3.5 delta b)."""
    names = {}
    skills_root = env.root / "skills"
    if not skills_root.is_dir():
        return names
    for bucket_dir in sorted(skills_root.iterdir()):
        if not bucket_dir.is_dir():
            continue
        for md in sorted(bucket_dir.rglob("SKILL.md")):
            fm = parse_frontmatter(md)
            name = fm.get("name") or md.parent.name
            names.setdefault(name, []).append(bucket_dir.name)
    return names


def name_duplicates(local_entries, registry_names):
    """Live local recordings, whose frontmatter `name` is already somewhere in the registry -
    duplicate NAME (not a catalog: for some skills the catalog was renamed when saved
    `name`, see `findings/P3-listing-hygiene-and-vendoring-facts.md` §6).

    Hub-managed ecosystem skills share registry names but are updated by
    the hub's memory-tool sync, not ``skiller update`` — exclude them from duplicate warnings."""
    return sorted(
        (e["dir"], e["name"], tuple(registry_names[e["name"]]))
        for e in local_entries
        if (not e["dead"] and e["name"] in registry_names
            and e["name"] not in MAIND_MANAGED_SKILL_NAMES)
    )


def raw_vendor_overlap_dirs(local_entries, registry_names, enabled_buckets):
    """Local entries raw vendor, whose names overlap the active ones marketplace-buckets.

    Used ``connect --cleanup-vendored`` for migration legacy symlinks from
    ``.ai/skills`` (repo fact insiders/flexcrm — channel without manifest)."""
    enabled = set(enabled_buckets)
    return sorted(
        e["dir"] for e in local_entries
        if (not e["dead"] and e["name"] in registry_names
            and e["name"] not in MAIND_MANAGED_SKILL_NAMES
            and enabled.intersection(registry_names[e["name"]]))
    )


def remove_raw_vendor_entries(skills_dir, dirs, *, dry_run=False):
    """Remove the listed entries from the directory raw vendor (symlink or directory)."""
    removed = []
    for name in dirs:
        path = skills_dir / name
        if not path.exists() and not path.is_symlink():
            continue
        if dry_run:
            removed.append(name)
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        removed.append(name)
    return removed


def dead_local_entries(local_entries):
    """Names of dead local entries (diagnostic: what exactly is dead)."""
    return sorted(e["dir"] for e in local_entries if e["dead"])


def prune_orphan_managed_lock(target, *, dry_run=False):
    """Remove managed-records skills-lock, whose installed_path no longer exist.

    Typical trace ``connect --cleanup-vendored``: physical. copies have been made lock stayed and
    is misleading the hub's project status / derive-graph."""
    lock_path = target / "skills-lock.json"
    if not lock_path.is_file():
        return 0
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    skills = data.get("skills")
    if not isinstance(skills, dict):
        return 0
    kept = {}
    orphans = []
    for name, entry in skills.items():
        if not entry.get("managed"):
            kept[name] = entry
            continue
        rel = entry.get("installed_path") or ""
        path = target / rel if rel else None
        if path is not None and path.exists():
            kept[name] = entry
        else:
            orphans.append(name)
    if not orphans:
        return 0
    if dry_run:
        print(f"NOTE: skills-lock: {len(orphans)} managed-records without files - "
              "delete: --cleanup-vendored (again)")
        return len(orphans)
    if kept:
        data["skills"] = kept
        atomic_write_json(lock_path, data)
    else:
        lock_path.unlink()
    print(f"Cleared skills-lock: removed {len(orphans)} orphan managed-records")
    return len(orphans)


def cmd_status(env, argv):
    opts = parse_flags(argv, {"--target": "str", "--json": "bool"})
    if opts["help"]:
        print("skiller status [--target DIR] [--json]")
        return
    js = opts.get("json")

    def out(s=""):                              # text - only in human readable mode
        if not js:
            print(s)

    if opts.get("target"):
        target = Path(os.path.expanduser(opts["target"])).resolve()
        via = "--target"
    else:
        target, via = find_project_root(env)
        if target is None:
            die("project root not found above CWD")
    config = load_config(env, target)
    out(f"Project:   {target} (by marker {via})")
    registered = {r["channel"] for r in db_records(env, target)}
    out(f"Registry:   {env.root}")
    out(f"B projects.json: "
        f"{', '.join(sorted(registered)) if registered else 'not registered'}")
    report = {"project": str(target), "via": via,
              "registered_channels": sorted(registered),
              "connect": None, "vendor": None, "budget": None, "channel_overlap": [],
              "dependency_closure": {"status": "unknown", "diagnostics": []},
              "measurements": {"status": "non-green", "rows": []}}

    enabled = []
    vendored_buckets = set()
    mk_file = detect_marketplace_file(target)
    if mk_file:
        s = json.loads((target / ".claude" / mk_file).read_text(encoding="utf-8"))
        src = s["extraKnownMarketplaces"][MARKETPLACE].get("source", {})
        # marketplace.json is in the ROOT of the monorepo (there connect/update write source),
        # and not in the package directory env.root — compare with the same root, otherwise in monorepo
        # eternal false [MOVED], which skiller update is not able to extinguish.
        mp_root = find_repo_root(env.root) or env.root
        moved = src != {"source": "directory", "path": str(mp_root)}
        out(f"\nChannel marketplace ({mk_file}):")
        out(f"  Source: {src.get('path', json.dumps(src))}"
            + ("  [MOVED - fix: skiller update]" if moved else ""))
        enabled = [k.split("@")[0] for k, v in s.get("enabledPlugins", {}).items()
                   if k.endswith(f"@{MARKETPLACE}") and v]
        disabled = [k.split("@")[0] for k, v in s.get("enabledPlugins", {}).items()
                    if k.endswith(f"@{MARKETPLACE}") and v is False]
        plugins, profile_name, _, source, include_meta = \
            resolve_selection(env, target, config, "", [])
        if include_meta and "generate-skill" not in plugins:
            plugins = list(plugins) + ["generate-skill"]
        missing = sorted(set(plugins) - set(enabled) - set(disabled))
        extra = sorted(set(enabled) - set(plugins))
        out(f"  Included: {' '.join(sorted(enabled)) or '-'}")
        if disabled:
            out(f"  Explicitly disabled: {' '.join(sorted(disabled))}")
        out(f"  Profile:  {profile_name or '-'} (via {source})")
        if missing:
            out(f"  Missing profile: {' '.join(missing)} "
                f"(add: skiller update)")
        if extra:
            out(f"  Over profile: {' '.join(extra)}")
        # included bucket merged into another (alias) — one hint line, without
        # discharge; status read-only, does not switch anything itself.
        alias_hints = alias_migration_hints(load_bucket_aliases(env), enabled)
        for h in alias_hints:
            out(f"  Hint: {h}")
        report["connect"] = {
            "marketplace_file": mk_file, "source": src.get("path", src), "moved": moved,
            "enabled": sorted(enabled), "disabled": sorted(disabled),
            "profile": profile_name, "source_via": source,
            "missing": missing, "extra": extra, "alias_hints": alias_hints}
    vendor_path = detect_vendor_path(target, config)
    raw_vendor_path = None
    local_entries = []
    if vendor_path:
        mf = target / vendor_path / MANIFEST
        manifest = json.loads(mf.read_text(encoding="utf-8"))
        skills = manifest.get("skills", [])
        gone = [e.get("source_path", "") for e in skills
                if e.get("source_path") and not (env.root / e["source_path"]).exists()]
        vendored_buckets = {b for e in skills
                            if (b := _bucket_of(e.get("source_path", "")))}
        out(f"\nChannel vendor ({vendor_path}, layout {manifest.get('layout')}):")
        out(f"  Skills: {len(skills)}, installed {manifest.get('installed_at')}"
            f", agent {manifest.get('agent')}, profile {manifest.get('profile') or '-'}")
        if gone:
            out(f"  Deleted/renamed in the registry ({len(gone)}): "
                + " ".join(gone[:5]) + (" …" if len(gone) > 5 else "")
                + "  (clean: skiller update)")
        report["vendor"] = {
            "path": vendor_path, "layout": manifest.get("layout"), "count": len(skills),
            "installed_at": manifest.get("installed_at"), "agent": manifest.get("agent"),
            "profile": manifest.get("profile"), "gone": gone}
        local_entries = local_channel_entries(target / vendor_path)
    else:
        # P3.5 delta a: channel without manifest (symlinks/copies from the side, not
        # via `skiller sync`) — was previously invisible to this command and to
        # channel_overlap (repo fact flexcrm: 58 records, no manifest).
        raw_vendor_path = detect_raw_vendor_path(target, config)
        if raw_vendor_path:
            local_entries = local_channel_entries(target / raw_vendor_path)
            live = [e for e in local_entries if not e["dead"]]
            out(f"\nChannel vendor ({raw_vendor_path}, WITHOUT manifest — not through "
                f"skiller sync/vendor):")
            out(f"  Entries: {len(local_entries)} ({len(live)} alive, "
                f"{len(local_entries) - len(live)} dead)")
    if not mk_file and not vendor_path and not raw_vendor_path:
        out("\nChannels: not connected (skiller connect | vendor)")

    dup = dead = []
    if local_entries:
        registry_names = registry_skill_names(env)
        dup = name_duplicates(local_entries, registry_names)
        dead = dead_local_entries(local_entries)
        if not vendor_path:
            # no manifest - only source "vendor buckets" for
            # channel_overlap below: name donor buckets that local shares with the registry.
            vendored_buckets = {b for _dir, _name, buckets in dup for b in buckets}
        if dup:
            out(f"\n⚠ DUPLICATE NAMES with registry ({len(dup)}): " + ", ".join(
                f"{d}→{'/'.join(b)}" for d, _n, b in dup[:8])
                + (" …" if len(dup) > 8 else ""))
            out("  Local copy is not updated `skiller update` — or remove "
                "local recording, or connect the donor bucket using a regular channel.")
        if dead:
            out(f"\n⚠ DEAD POSTS ({len(dead)}): broken symlinks/directories without "
                "SKILL.md — " + ", ".join(dead[:8]) + (" …" if len(dead) > 8 else ""))
            out("  Clean: find <channel> -maxdepth 1 -xtype l -delete "
                "(check the list above before mass deletion).")
    report["name_duplicates"] = [{"dir": d, "name": n, "buckets": list(b)}
                                  for d, n, b in dup]
    report["dead_entries"] = dead

    # Set token budget (bloat control): ⊕ always — permanent tax
    # descriptions, resident in each request. Details/map - skiller budget.
    try:
        skills, meta = resolve_active_set(env, target, config)
        b = budget_for_set(skills, meta["pulled"])
        top = sorted(b["items"], key=lambda i: i["tier0"], reverse=True)[:3]
        out(f"\nSet token budget (≈, profile {meta['profile'] or '-'}):")
        out(f"  ⊕ always {b['tier0']} current · ↻ bodies {b['tier1']} current · "
            f"{b['count']} skills  (details: skiller budget)")
        if top:
            out("  Top ⊕: " + ", ".join(
                f"{i['name']} ({i['tier0']})" for i in top))
        report["budget"] = {"tier0": b["tier0"], "tier1": b["tier1"], "count": b["count"],
                            "profile": meta["profile"],
                            "top": [{"name": i["name"], "tier0": i["tier0"]} for i in top]}
        dependency_diagnostics = meta["dependency_diagnostics"]
        report["dependency_closure"] = {
            "status": "non-green" if dependency_diagnostics else "green",
            "diagnostics": dependency_diagnostics,
        }
        report["measurements"] = listing_measurements(skills)
    except SystemExit:
        raise
    except Exception as e:  # the budget should not be dropped status
        out(f"\nToken budget: unavailable ({e})")

    # Channel hygiene: one bucket should not be distributed by BOTH the plugin AND the vendor -
    # otherwise the skills are duplicated. Check lives ONLY here (skiller — owner
    # skills); umbrella pulls her through `swissknifeman skills status`, without duplicating.
    overlap = channel_overlap(enabled, vendored_buckets)
    report["channel_overlap"] = overlap
    if overlap:
        out(f"\n⚠ DOUBLE CHANNELS: buckets [{' '.join(overlap)}] are active AT THE SAME TIME as "
            f"plugins (connect) and vendors (vendor) — skills are distributed twice.")
        out("  Leave one channel: remove the bucket from enabledPlugins (connect) OR from "
            ".swissknifeman/config.json (vendor) + skiller sync.")
    if js:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print()
    print_registry_state(env)
