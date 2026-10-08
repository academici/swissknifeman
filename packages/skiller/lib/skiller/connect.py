"""connect — channel plugin marketplace Claude Code."""
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from core import (apply_plan, atomic_write_text, find_repo_root, parse_lock,
                  safe_load_json, serialize_lock)
from core.provider.lock import ArtifactLock, LOCK_RELATIVE_PATH
from core.provider.artifact import sha256_digest

from aicore.delivery.claude import enable_marketplace_plugins, redacted_settings_preview

from .common import (AGENT_DEFAULTS, MANIFEST, MARKETPLACE, apply_permissions,
                     die, is_within, parse_flags, warn)
from .config import (CORE_BUCKETS, CORE_PLUGIN, CORE_SKILLS,
                     all_buckets, default_command_plugins,
                     load_config, resolve_selection, resolve_target)
from .hub import generate_hub, hub_artifacts_exist
from .state import upsert_project
from .publication import build_connect_distribution_plan, selected_distribution_providers


def _prune_codex_connect_artifacts(target, *, dry_run):
    """Remove only the prior Codex Connect bundle owned by its artifact lock.

    A new explicit plugin selection is a replacement, not an accumulation.  The
    provider lock may also track Claude/other artifacts, so retain every record
    outside `.agents/plugins` owned by Codex Connect.
    """
    lock_path = target / LOCK_RELATIVE_PATH
    if not lock_path.is_file():
        return
    try:
        lock = parse_lock(lock_path.read_bytes())
    except (OSError, ValueError) as exc:
        die(f"SPUB_OWNERSHIP_CONFLICT: provider codex, invalid artifact lock {lock_path}: {exc}")
    prefix = ".agents/plugins/"
    stale = tuple(record for record in lock.records
                  if record.artifact_id.startswith("skiller.codex.connect.")
                  and record.provider_id.value == "codex"
                  and record.target_path.startswith(prefix))
    if not stale:
        return
    # Validate every preimage before deleting any owned artifact.
    for record in stale:
        path = target / record.target_path
        if (path.is_symlink() or (path.exists() and
                (not path.is_file() or sha256_digest(path.read_bytes()) != record.rendered_hash))):
            die(f"SPUB_OWNERSHIP_CONFLICT: provider codex, modified prior artifact: {path}")
    if dry_run:
        print(f"--- dry-run: prune {len(stale)} prior Codex Connect artifact(s) ---")
        return
    for record in stale:
        path = target / record.target_path
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            die(f"SPUB_OWNERSHIP_CONFLICT: provider codex, expected file artifact is a directory: {path}")
    retained = tuple(record for record in lock.records if record not in stale)
    atomic_write_text(lock_path, serialize_lock(ArtifactLock(lock.schema_version, retained)).decode("utf-8"))
    bundles = target / ".agents/plugins/bundles"
    if bundles.is_dir():
        for directory in sorted((item for item in bundles.rglob("*") if item.is_dir()), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            bundles.rmdir()
        except OSError:
            pass


def prepare_connect_selection(env, target, opts, config):
    """Resolve the one semantic plugin set used by every selected provider."""
    flag_plugins = [p for p in opts.get("plugins", "").split(",") if p]
    plugins, profile_name, profile_source, source, include_meta = \
        resolve_selection(env, target, config, opts.get("profile", ""), flag_plugins)
    if profile_source == "items":
        profile_source = "plugins"

    buckets = all_buckets(env)
    command_plugins = default_command_plugins()
    known_plugins = (set(buckets) | {"generate-skill", CORE_PLUGIN}
                     | set(command_plugins))
    core_added = []
    if not opts.get("no_core") and CORE_PLUGIN not in plugins:
        if _marketplace_declares(env, CORE_PLUGIN):
            core_added = [CORE_PLUGIN]
            plugins = list(plugins) + core_added
        else:
            warn(f"marketplace '{MARKETPLACE}' does not declare the plugin '{CORE_PLUGIN}' — "
                 f"core (CORE_SKILLS) NOT delivered. Drive away `skiller registry` in "
                 f"registry, then repeat connect (or --no-core, if this is conscious).")

    if CORE_PLUGIN in plugins and "general" in plugins:
        plugins = [plugin for plugin in plugins if plugin != "general"]
        warn("plugin 'general' excluded: him CORE-already supplies skills 'core'; "
             "for complete general use --no-core")

    cmd_added = []
    for cp in command_plugins:
        if cp not in plugins and _marketplace_declares(env, cp):
            cmd_added.append(cp)
    plugins = list(plugins) + cmd_added

    for plugin in plugins:
        if plugin not in known_plugins:
            die(f"unknown plugin: {plugin} (available: {', '.join(sorted(known_plugins))})")
    if include_meta and "generate-skill" not in plugins:
        plugins = list(plugins) + ["generate-skill"]
    return {
        "plugins": tuple(sorted(set(plugins))),
        "profile_name": profile_name,
        "profile_source": profile_source,
        "source": source,
        "include_meta": include_meta,
        "core_added": tuple(core_added),
        "cmd_added": tuple(cmd_added),
    }


# Compatibility for callers/tests that used the former private seam.  Doctor uses the
# public helper so its read-only preflight resolves exactly the selection connect applies.
_prepare_connect_selection = prepare_connect_selection


def _resident_tokens(env, plugins):
    """Rough estimate of resident ⊕ tier-0 (name+description) of the selected set of plugins -
    for «smart connection»: you can see the price BEFORE recording. core → CORE_SKILLS; bucket → all his skills;
    generate-skill → his skill. Source of token mathematics ONE - aicore.content.budget.skill_budget, re-exported by budget (do not duplicate).
    Return (tokens, n_skills)."""
    from .budget import skill_budget
    total = n = 0
    for p in plugins:
        if p == CORE_PLUGIN:
            dirs = [env.root / "skills" / cs for cs in CORE_SKILLS]
        elif p == "generate-skill":
            dirs = [env.root / "generate-skill" / "generate-skill"]
        else:
            base = env.root / "skills" / p
            dirs = [d for d in base.iterdir() if d.is_dir()] if base.is_dir() else []
        for d in dirs:
            b = skill_budget(d)
            if b:
                total += b["tier0"]
                n += 1
    return total, n


def _marketplace_declares(env, plugin_name):
    """True, if generated marketplace.json (in the root of the repo) announces plugin_name.
    Protection: old marketplace or in a curated synthetic test registry `core` may
    not to be - then CORE-politics doesn't push him quietly (as before for missing buckets)."""
    mp = (find_repo_root(env.root) or env.root) / ".claude-plugin" / "marketplace.json"
    data = safe_load_json(mp, default={}) or {}
    return any(p.get("name") == plugin_name for p in data.get("plugins", []))


def _do_connect_claude(env, target, opts, register=True, fix_path_drift=False,
                       prepared=None):
    root = env.root
    config = load_config(env, target)
    prepared = prepared or prepare_connect_selection(env, target, opts, config)
    plugins = list(prepared["plugins"])
    profile_name = prepared["profile_name"]
    profile_source = prepared["profile_source"]
    source = prepared["source"]
    # CORE-policy (smart connection): instead of whole buckets general(19)+oss-dev(10) ≈ 1956
    # push resident tokens lightweight curated plugin `core` (== CORE_SKILLS) — savings
    # even with the current lineup (8 skills, ~696 current according to calibrated constants budget.py —
    # see `skiller budget --check-core` for the actual figure, not a hardcode snapshot here,
    # see T-2 audit: «7 ≈ 480» went bad when CORE_SKILLS increased to 8). --no-core disables.
    # The plugin is declared in marketplace (registry.py); on the old one marketplace / in the test registry
    # it may not exist - then we skip it with an explicit warn (see below, audit C-1).
    core_added = list(prepared["core_added"])

    # Default command plugins (task): is included in EVERY project, as core. Marketplace-guarded
    # (on the old one marketplace / in the test registry we silently skip). --no-core does NOT touch them - this is not
    # CORE-skills; you can disable it point by point enabledPlugins[...]=false.
    cmd_added = list(prepared["cmd_added"])

    if config.exclude:
        print("NOTE: .swissknife.json 'exclude' is skill-granular and is ignored "
              "in plugin mode (plugins are bucket-granular)")

    print(f"Target:   {target}")
    print(f"Profile:  {profile_name or '-'} (via {source})")
    print(f"Source:   {root}")
    print(f"Plugins:  {' '.join(plugins)}")
    resident, n_res = _resident_tokens(env, plugins)
    print(f"Resident: ~{resident} current ⊕ tier-0 ({n_res} skills, name+description in EACH "
          f"request; body - by trigger). Less = cheaper: already a profile or --no-core.")
    if source == "autodetect-fallback":
        print("⚠ ATTENTION: project type not recognized - MINIMUM set supplied (core),\n"
              "  and not «everything». For optimal dialing, specify the profile explicitly:\n"
              "  skiller connect --profile <node-frontend|laravel-project|php-package|…>\n"
              "  or the exact list: skiller connect --plugins a,b,c")
    if core_added:
        print(f"CORE:     {CORE_PLUGIN} (lightweight token-saving core, {len(CORE_SKILLS)} skills "
              f"instead of buckets general+oss-dev; --no-core disables)")
    if cmd_added:
        print(f"COMMANDS: {' '.join(cmd_added)} (host command plugins, are distributed by default; "
              f"disable pointwise - enabledPlugins[...]=false)")

    list_only = opts.get("list", False)
    dry_run = opts.get("dry_run", False)
    if list_only:
        return None

    settings_file = opts.get("file") or "settings.local.json"
    if settings_file not in ("settings.json", "settings.local.json"):
        die("--file should be settings.json or settings.local.json")
    dest = target / ".claude" / settings_file
    settings = {}
    if dest.exists():
        try:
            settings = json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{dest}: invalid JSON: {e}")

    # Marketplace source paths are relative to the host root where registry writes
    # its manifest, including sibling plugin entries declared by the host config.
    mp_root = find_repo_root(root) or root
    merged = enable_marketplace_plugins(settings, marketplace=MARKETPLACE, marketplace_root=mp_root,
                                        plugins=plugins, fix_path_drift=fix_path_drift)
    for note in merged.notes:
        print(note)
    enabled = settings["enabledPlugins"]
    added, skipped_false, drift = merged.added, merged.skipped_false, merged.drift

    if dry_run:
        print(f"--- dry-run: {dest} ---")
        print(json.dumps(redacted_settings_preview(settings), ensure_ascii=False, indent=2))
    else:
        if dest.exists():
            shutil.copy2(dest, f"{dest}.bak")
            print(f"Backup:    {dest}.bak")
        atomic_write_text(dest,
                          json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        print(f"Recorded: {dest}")

    if added:
        print(f"Included: {' '.join(added)}")
    if skipped_false:
        print(f"Skipped (explicit false): {' '.join(skipped_false)}")
    if drift:
        print(f"NOTE: included in addition to the profile (I don't touch): {' '.join(drift)}")

    # Migration from old CORE-policies (whole buckets general+oss-dev) to easy core-plugin:
    # if they remain enabled OUTSIDE the active profile - now this is an extra resident weight
    # (already gives them 7 token skills `core`). We suggest you remove it; merge-only — we don’t touch it ourselves.
    if core_added:
        legacy = [b for b in CORE_BUCKETS
                  if enabled.get(f"{b}@{MARKETPLACE}") and b not in plugins]
        if legacy:
            print(f"NOTE: old CORE-buckets are included in addition to the profile: {' '.join(legacy)} — now "
                  f"replaces them with light '{CORE_PLUGIN}'. To save tokens, disable them in "
                  f"{settings_file}: \"{legacy[0]}@{MARKETPLACE}\": false (etc.)")

    # permissions-presets (deny garbage + allow stack) at the same settings-file
    if not opts.get("no_permissions"):
        apply_permissions(env, target, settings_file=settings_file, dry_run=dry_run)

    # vendored-copy migration
    skills_path = config.skills_path or AGENT_DEFAULTS["claude"]
    # The three-provider config may point at the Codex projection while an old
    # Claude vendor tree still lives at its historical default.  Inspect both
    # locations so switching config cannot hide a managed legacy manifest.
    manifest_files = {
        target / skills_path / MANIFEST,
        target / AGENT_DEFAULTS["claude"] / MANIFEST,
    }
    legacy_manifest_found = False
    for manifest_file in sorted(manifest_files):
        if not manifest_file.exists():
            continue
        legacy_manifest_found = True
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        dest_root = manifest_file.parent
        stale = []
        for entry in manifest.get("skills", []):
            name = entry.get("flat_name") or entry.get("path", "")
            d = dest_root / name
            if name and d.is_dir() and is_within(d, dest_root):
                stale.append(d)
        if opts.get("cleanup_vendored") and not dry_run:
            for d in stale:
                shutil.rmtree(d)
            manifest_file.unlink()
            print(f"Vendor copies removed: {len(stale)} skill dir(s) + manifest")
        else:
            print(f"NOTE: vendor copies found ({len(stale)} dir(s) in "
                  f"{dest_root}) — delete: --cleanup-vendored")

    if opts.get("cleanup_vendored"):
        from .status import (detect_raw_vendor_path, local_channel_entries,
                             prune_orphan_managed_lock, raw_vendor_overlap_dirs,
                             registry_skill_names, remove_raw_vendor_entries)
        raw_path = detect_raw_vendor_path(target, config)
        if raw_path:
            skills_dir = target / raw_path
            local_entries = local_channel_entries(skills_dir)
            enabled_buckets = {k.split("@")[0] for k, v in enabled.items()
                                 if k.endswith(f"@{MARKETPLACE}") and v}
            overlap_dirs = raw_vendor_overlap_dirs(
                local_entries, registry_skill_names(env), enabled_buckets)
            if overlap_dirs:
                if dry_run:
                    print(f"NOTE: raw vendor ({raw_path}) overlaps marketplace: "
                          f"{' '.join(overlap_dirs)} — delete: --cleanup-vendored")
                else:
                    removed = remove_raw_vendor_entries(
                        skills_dir, overlap_dirs, dry_run=False)
                    print(f"Deleted raw vendor-records ({raw_path}): "
                          f"{len(removed)} ({', '.join(removed[:8])}"
                          f"{', …' if len(removed) > 8 else ''})")
            elif not legacy_manifest_found:
                print(f"NOTE: raw vendor ({raw_path}) without intersections with marketplace "
                      f"— project-specific entries saved")
        prune_orphan_managed_lock(target, dry_run=dry_run)

    hub = opts.get("hub", False)
    if hub and not dry_run and not opts.get("native_codex"):
        generate_hub(env, target)
    elif not hub and not dry_run:
        print("Hint: root skill hub - skiller update or "
              "restart from --hub")

    record = {
        "path": str(target),
        "channel": "marketplace",
        "profile": profile_name,
        "profile_source": profile_source,
        "plugins": plugins,
        "settings_file": settings_file,
        "hub": hub or hub_artifacts_exist(target),
        "provider": "claude-code",
    }
    if register and not dry_run:
        upsert_project(env, record)

    print("Next: restart the session Claude Code in the project "
          "(or /plugin marketplace update swissknifeman)")
    return record


def _preflight_claude_connect_target(target, opts):
    settings_file = opts.get("file") or "settings.local.json"
    if settings_file not in ("settings.json", "settings.local.json"):
        die("--file should be settings.json or settings.local.json")
    dest = target / ".claude" / settings_file
    if dest.exists():
        try:
            json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            die(f"{dest}: invalid JSON: {exc}")


def _apply_codex_connect_plan(env, target, plan, *, dry_run, register):
    if plan.channel == "marketplace":
        print(f"Codex marketplace: {plan.target} "
              "(self-host generated projection; native install is explicit)")
    else:
        if dry_run:
            print(f"--- dry-run: Codex marketplace bundle → {plan.target} ---")
        else:
            try:
                apply_plan(target, plan.artifact_plan)
            except (OSError, ValueError) as exc:
                die("SPUB_OWNERSHIP_CONFLICT: provider codex, "
                    f"channel marketplace-bundle, target {target}: {exc}")
            print(f"Codex marketplace: {plan.target} "
                  "(project-scoped contained bundles; install/enable remains explicit)")
    record = {
        "path": str(target),
        "channel": "marketplace",
        "provider": "codex",
        "target": str(plan.target),
        "source_hash": plan.source_hash,
        "rendered_hash": plan.rendered_hash,
        "hub": hub_artifacts_exist(target),
    }
    if register and not dry_run:
        upsert_project(env, record)
    return record


def do_connect(env, target, opts, register=True, fix_path_drift=False):
    """Apply a preflighted provider marketplace plan.

    The legacy Claude writer remains byte-compatible.  Codex self-host delivery
    is intentionally a verified generated marketplace, not a second settings
    format or an implicit global install.
    """
    if opts.get("native_codex") or opts.get("native_codex_only"):
        # Activation selection never changes the project's permission policy.
        opts = {**opts, "native_codex": True, "no_permissions": True}
    config = load_config(env, target)
    repo_root = find_repo_root(env.root) or env.root
    prepared = prepare_connect_selection(env, target, opts, config)
    native_plan = None
    if opts.get("native_codex"):
        from .native_codex import plan_selection
        marketplace = json.loads((repo_root / ".agents/plugins/marketplace.json").read_text())
        try:
            native_plan = plan_selection(env, target, prepared["plugins"],
                                         [p["name"] for p in marketplace["plugins"]])
        except (OSError, ValueError) as exc:
            die(f"CODEX_SELECTION_PREFLIGHT: {exc}")
    if opts.get("native_codex_only"):
        from .native_codex import apply_selection
        apply_selection(target, native_plan, dry_run=opts.get("dry_run", False))
        return {"provider": "codex", "target": str(native_plan["path"]),
                "plugins": native_plan["selected"]}
    if "codex" in selected_distribution_providers(config, project_id=target.name):
        _prune_codex_connect_artifacts(target, dry_run=opts.get("dry_run", False))
    if (opts.get("dry_run", False) and target.resolve() != repo_root.resolve()
            and (target / LOCK_RELATIVE_PATH).is_file()
            and "codex" in selected_distribution_providers(config, project_id=target.name)):
        # The write path plans after pruning. Mirror only that surface so dry-run
        # sees the same post-prune files and lock without changing the consumer.
        with tempfile.TemporaryDirectory(prefix="skiller-connect-preflight-") as folder:
            snapshot = Path(folder)
            bundles = target / ".agents/plugins"
            if bundles.is_dir():
                shutil.copytree(bundles, snapshot / ".agents/plugins", symlinks=True)
            snapshot_lock = snapshot / LOCK_RELATIVE_PATH
            snapshot_lock.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / LOCK_RELATIVE_PATH, snapshot_lock)
            _prune_codex_connect_artifacts(snapshot, dry_run=False)
            plans = build_connect_distribution_plan(
                config, snapshot, project_id=target.name, repo_root=repo_root,
                plugins=prepared["plugins"])
            plans = tuple(replace(plan, target=target / plan.target_identity) for plan in plans)
    else:
        plans = build_connect_distribution_plan(config, target, project_id=target.name,
                                                repo_root=repo_root,
                                                plugins=prepared["plugins"])
    if any(plan.provider_id == "claude-code" for plan in plans):
        _preflight_claude_connect_target(target, opts)
    records = []
    for plan in plans:
        if plan.provider_id == "claude-code":
            records.append(_do_connect_claude(env, target, opts, register=register,
                                              fix_path_drift=fix_path_drift,
                                              prepared=prepared))
        elif plan.provider_id == "codex":
            records.append(_apply_codex_connect_plan(
                env, target, plan, dry_run=opts.get("dry_run", False),
                register=register))
    if native_plan is not None:
        from .native_codex import apply_selection
        apply_selection(target, native_plan, dry_run=opts.get("dry_run", False))
        if opts.get("hub") and not opts.get("dry_run", False):
            generate_hub(env, target, root_files=("AGENTS.md",))
    return records[0] if len(records) == 1 else {"providers": records}


def cmd_connect(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--profile": "str", "--plugins": "str",
        "--file": "str", "--cleanup-vendored": "bool", "--cleanup-codex-vendored": "bool",
        "--cleanup-codex-physical": "bool", "--list": "bool",
        "--dry-run": "bool", "--hub": "bool", "--no-core": "bool",
        "--no-permissions": "bool", "--fix-path": "bool",
        "--native-codex": "bool", "--cleanup-codex-links": "bool",
        "--cleanup-codex-equivalent-links": "bool",
        "--native-codex-only": "bool",
    })
    if opts["help"]:
        print("skiller connect [--profile P|--plugins a,b] "
              "[--file settings.json|settings.local.json] [--cleanup-vendored] "
              "[--list] [--dry-run] [--hub] [--no-core] [--no-permissions] "
              "[--cleanup-codex-vendored] [--cleanup-codex-links] [--cleanup-codex-equivalent-links] [--cleanup-codex-physical] "
              "[--fix-path] [--native-codex|--native-codex-only]\n"
              "  --native-codex-only: only changes project .codex/config.toml according to current "
              "profile; doesn't write distribution, permissions or state.")
        return
    target, _ = resolve_target(env, opts, allow_home_confirm=True)
    do_connect(env, target, opts, fix_path_drift=opts.get("fix_path", False))
    if opts.get("cleanup_codex_vendored"):
        from .update import retire_legacy_codex_vendor
        retire_legacy_codex_vendor(env, target, dry_run=opts.get("dry_run", False))
    if opts.get("cleanup_codex_links"):
        from .update import retire_legacy_codex_links
        retire_legacy_codex_links(env, target, dry_run=opts.get("dry_run", False))
    if opts.get("cleanup_codex_equivalent_links"):
        from .update import retire_equivalent_codex_skill_links
        retire_equivalent_codex_skill_links(env, target, dry_run=opts.get("dry_run", False))
    if opts.get("cleanup_codex_physical"):
        from .update import retire_orphan_codex_physical_skills
        retire_orphan_codex_physical_skills(env, target, dry_run=opts.get("dry_run", False))
