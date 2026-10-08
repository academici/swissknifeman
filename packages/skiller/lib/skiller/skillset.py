"""skillset — vendor-mode on a single config.swissknifeman/config.json.

A single source of truth for the physical transfer of skills to the project: config in
`.swissknifeman/config.json` sets the rules (specific skills + entire buckets −
exceptions), `sync` expands them into a flat set, copies the files to the repo and
writes derivative `skills-lock.json` with a mark of origin.

Stream (config → lock → files):

    .swissknifeman/config.json   (source of truth, man rules)
            ↓ resolve_skillset    turning the rules into a flat set of skills
       set of skills from the library swissknifeman (by skills.json)
            ↓ sync_skillset       install + update(by sha256) + prune(by managed)
    .claude/skills/<name>/        physical copies (sees Claude)
    skills-lock.json             derived map: managed-records + aliens untouched

Safe removal: prune touches records ONLY managed=true, which no longer exist
in the config. Alien skills (managed missing/false — handmade vendoring, heritage
Boost, skills from another hub) does not delete the sync. See [[lock]] — read-only composer
remains for projects without vendor-mode.
"""
import functools
import json
from pathlib import Path

from core.io import atomic_write_json

# The lock, the managed copies and the sync that applies a plan: moved to aicore.delivery.materialize,
# re-exported under the historical names (after the first ``core`` import, which puts aicore on sys.path).
from aicore.delivery.materialize import (  # noqa: F401
    GITIGNORE_HEADER, LOCK_FILE, LOCK_VERSION, SOURCE, dir_sha256 as _dir_sha256,
    hash_label as _hash_label, load_lock, lock_problem as _lock_problem,
    remove_our_gitignore as _remove_our_gitignore, remove_path as _remove_path,
    safe_copy_skill, sync_report_counts as _sync_report_counts, write_gitignore as _write_gitignore,
    write_lock, write_manifest as _write_manifest)
from aicore.delivery.materialize import sync_skillset as _sync_skillset

from .common import apply_permissions, die, parse_flags, resolve_requires_bfs, warn
from .config import (DEFAULT_EXCLUDE, all_buckets, core_skill_tuples,
                     load_config, resolve_selection, resolve_target)
from .hub import generate_hub, hub_artifacts_exist
from .state import upsert_project

# Where do we add the default skills? (Claude finds automatically).
DEFAULT_SKILLS_PATH = ".claude/skills"
CONFIG_DIR = ".swissknifeman"
CONFIG_FILE = "config.json"

# Config keys vendor-mode (.swissknifeman/config.json). Intentionally wider
# .swissknife.json — is a separate, extensible physical mode config. transfer.
SKILLSET_KEYS = {
    "version": int,
    "mode": str,          # only for now "vendor"
    "agent": str,         # informative; sets the path skills_path
    "skills_path": str,   # where to copy (default .claude/skills)
    "presets": list,      # named clusters (presets/<name>.json) → buckets/include
    "include": list,      # specific skills: "bucket/rel" or simply "name"
    "buckets": list,      # entire buckets
    "exclude": list,      # subtraction from (presets ∪ buckets ∪ include)
    "gitignore_managed": bool,  # issue <skills_path>/.gitignore for managed-skills
}



# --- private/source-only buckets ------
def private_source_buckets(env):
    """Buckets marked `private_source_only` in buckets.json (now: exactly
    `repository-bootstrap`, class A root-bootstrap identities) — their records are NEVER
    fall into none consumer-set (`include`/`buckets`/transitive `requires`),
    regardless of what token they were requested with. `skillset.py` implements ONLY
    this consumer-exception - he is never a producer root-projections (see
    `semantic-identity-ownership-v1.md`, `publication.py` root-bootstrap renderer)."""
    meta_file = env.root / "buckets.json"
    if not meta_file.is_file():
        return frozenset()
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return frozenset()
    if not isinstance(meta, dict):
        return frozenset()
    return frozenset(name for name, data in meta.items()
                     if isinstance(data, dict) and data.get("private_source_only"))


# --- registry index (source of truth - skills.json) ---------------------------
def _registry_index(env):
    """skills.json → {key: entry}, where key — and full path 'bucket/rel', and name.

    entry = {name, bucket, rel, path(SKILL.md, rel. registry root), sha256,
             skill_dir(abs.)}. The registry is the only source for
    our skills are resolved and checked for drift. Posts private-source-only buckets
 are excluded here, at the SINGLE entry point - so `include` by name,
    `buckets` entire and transitive `requires` can't reach them with any
    by (see `private_source_buckets`)."""
    f = env.root / "skills.json"
    if not f.is_file():
        die("skills.json not found - first skiller registry")
    data = json.loads(f.read_text(encoding="utf-8"))
    skills = data["skills"] if isinstance(data, dict) else data
    private_buckets = private_source_buckets(env)
    by_key = {}
    by_name = {}
    for s in skills:
        name = s.get("name") or s.get("id")
        bucket = s.get("bucket", "")
        path = s.get("path", "")  # "skills/<bucket>/<rel>/SKILL.md"
        if not (name and path):
            warn(f"skills.json: entry skipped (missing name or path): {s}")
            continue
        if bucket in private_buckets:
            continue
        skill_dir = (env.root / path).parent
        # rel inside the bucket: skills/<bucket>/<rel>/SKILL.md → <rel>
        rel = ""
        parts = Path(path).parts
        if len(parts) >= 4 and parts[0] == "skills":
            rel = "/".join(parts[2:-1])
        entry = {
            "name": name, "bucket": bucket, "rel": rel, "path": path,
            "sha256": s.get("sha256", ""),
            "content_sha256": s.get("content_sha256", ""),
            "requires": s.get("requires", []) or [],
            "skill_dir": skill_dir,
        }
        full = f"{bucket}/{rel}".rstrip("/") if rel else bucket
        by_key[full] = entry
        if name in by_name:
            warn(f"skills.json: double name '{name}' "
                 f"(buckets: {by_name[name]['bucket']} and {bucket}) — by name "
                 f"available first; use full path 'bucket/rel'")
        else:
            by_name[name] = entry
    return by_key, by_name


def _match(token, by_key, by_name):
    """Allow rule token in entry: first by full path, then by name.

    Drift-resilience: after splitting buckets the old way 'oldbucket/skill'
    (e.g. 'frontend/vue' → 'frontend-vue/vue') misses by_key. If
    token - path, finish by base name (last segment). Otherwise sync
    silently lost skills that moved (warn+skip). Caller types
    migration-warning with old→in a new way."""
    if token in by_key:
        return by_key[token]
    if token in by_name:
        return by_name[token]
    if "/" in token:
        base = token.rsplit("/", 1)[1]
        if base in by_name:
            return by_name[base]
    return None


# --- presets (named skill clusters) -----------------------------------
def _load_preset(env, name):
    """presets/<name>.json or None. Invalid JSON — die."""
    f = env.root / "presets" / f"{name}.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        die(f"presets/{name}.json: invalid JSON: {e}")


def resolve_presets(env, names):
    """Expand presets (recursively `extends`) in (buckets, include, skipped).

    Preset - named group: `{name, description, extends?, buckets?, include?}`.
    Returns aggregated buckets/include (with grandfather, parents before children) and
    skipped — unknown presets (warning). Loop `extends` — die."""
    buckets, include, skipped, seen = [], [], [], set()

    def visit(name, trail):
        if name in trail:
            die(f"presets: loop extends: {' -> '.join(trail + [name])}")
        if name in seen:
            return
        preset = _load_preset(env, name)
        if preset is None:
            warn(f"presets: preset '{name}' not found in presets/ — pass")
            skipped.append(name)
            return
        seen.add(name)
        for parent in preset.get("extends", []):
            visit(parent, trail + [name])
        buckets.extend(preset.get("buckets", []))
        include.extend(preset.get("include", []))

    for n in names:
        visit(n, [])
    return buckets, include, skipped


# --- config -------------------------------------------------------------------
def skillset_config_path(target):
    return Path(target) / CONFIG_DIR / CONFIG_FILE


def load_skillset_config(target):
    """Read .swissknifeman/config.json (or None, if it's not there)."""
    cfg_file = skillset_config_path(target)
    if not cfg_file.is_file():
        return None
    try:
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{cfg_file}: invalid JSON: {e}")
    import difflib
    for key, value in cfg.items():
        if key.startswith(("_", "$")):  # _comment / $schema — DX, not validated
            continue
        if key not in SKILLSET_KEYS:
            hint = difflib.get_close_matches(key, list(SKILLSET_KEYS), n=1)
            suffix = f" — maybe '{hint[0]}'?" if hint else ""
            die(f"{cfg_file}: unknown key '{key}'{suffix}")
        if not isinstance(value, SKILLSET_KEYS[key]):
            want = SKILLSET_KEYS[key].__name__
            die(f"{cfg_file}: '{key}' should be {want}")
    if cfg.get("mode", "vendor") != "vendor":
        die(f"{cfg_file}: is only supported mode=vendor")
    return cfg


def _pull_requires(selected, by_name, exclude, *, diagnostics=None):
    """Transitively hold out `requires` selected skills in `selected` (name->entry).
    exclude CONQUERS addiction (with warning), unknown dependency - warning and
    pass. Without this skill-granular include was silently losing dependencies (64/195
    skills have requires). BFS — shared with vendor.resolve_requires via
    common.resolve_requires_bfs (V-1: previously two independent, already diverged bodies)."""
    seed = [(dep, e["name"]) for e in list(selected.values())
            for dep in e.get("requires", [])]
    selected_keys = set(selected.keys())

    def lookup(dep):
        entry = by_name.get(dep)
        if entry is None:
            return None
        full = (f"{entry['bucket']}/{entry['rel']}".rstrip("/")
                if entry["rel"] else entry["bucket"])
        tokens = {dep, entry["name"], full, entry["bucket"]}
        return {"key": entry["name"], "requires": entry.get("requires", []),
                "exclude_tokens": tokens, "_payload": entry}

    for node, _requester in resolve_requires_bfs(
            seed, lookup, selected_keys, exclude, diagnostics=diagnostics):
        selected[node["key"]] = node["_payload"]


def resolve_skillset(env, cfg, include_core=False, *, diagnostics=None):
    """Expand config rules into a set entry: (buckets ∪ include) − exclude,
    then transitively hold out `requires` (exclude still wins).

    include_core=True adds CORE_SKILLS (like vendor/connect) and applies
    DEFAULT_EXCLUDE — token skills are distributed to each project by default.

    Returns (entries, skipped): entries sorted by 'bucket/name';
    skipped — tokens not found in the registry (with warning)."""
    by_key, by_name = _registry_index(env)
    known = set(all_buckets(env))
    selected = {}  # name -> entry (name is unique in the layout.claude/skills)
    skipped = []

    # open presets in buckets/include BEFORE formula (buckets ∪ include) − exclude
    preset_buckets, preset_include, preset_skipped = \
        resolve_presets(env, cfg.get("presets", []))
    skipped.extend(preset_skipped)
    req_buckets = list(dict.fromkeys(preset_buckets + cfg.get("buckets", [])))
    req_include = list(dict.fromkeys(preset_include + cfg.get("include", [])))

    # entire buckets
    private_buckets = private_source_buckets(env)
    for bucket in req_buckets:
        if bucket in private_buckets:
            die(f"bucket '{bucket}' private source-only (repository-bootstrap, P1.2/D31) — "
                f"his entries are not vendor'/connect'are added to consumer projects")
        if bucket not in known:
            die(f"unknown bucket: {bucket}")
        for entry in by_key.values():
            if entry["bucket"] == bucket:
                selected[entry["name"]] = entry

    # specific skills
    for token in req_include:
        entry = _match(token, by_key, by_name)
        if entry is None:
            warn(f"include: skill '{token}' not found in the registry - skip")
            skipped.append(token)
            continue
        full = (f"{entry['bucket']}/{entry['rel']}".rstrip("/")
                if entry["rel"] else entry["bucket"])
        if "/" in token and token != full:
            warn(f"include: '{token}' moved → '{full}' (split buckets) — "
                 f"update .swissknifeman/config.json")
        selected[entry["name"]] = entry

    # CORE-policy: default token skills + DEFAULT_EXCLUDE hub duplicates
    exclude = set(cfg.get("exclude", []))
    if include_core:
        exclude |= set(DEFAULT_EXCLUDE)
        for _bucket, _rel, _d, fm_name in core_skill_tuples(env, exclude):
            entry = by_name.get(fm_name)
            if entry:
                selected[entry["name"]] = entry

    # subtraction
    if exclude:
        for name, entry in list(selected.items()):
            full = f"{entry['bucket']}/{entry['rel']}".rstrip("/") \
                if entry["rel"] else entry["bucket"]
            if {name, full, entry["bucket"], entry["rel"]} & exclude:
                del selected[name]

    # transitive requires selected skills (after subtraction: pulling dependencies
    # only those that will actually remain). exclude still beats addiction.
    _pull_requires(selected, by_name, exclude, diagnostics=diagnostics)

    entries = sorted(selected.values(),
                     key=lambda e: (e["bucket"], e["name"]))
    return entries, skipped


# --- sync ---------------------------------------------------------------------
def plan_sync(env, target, cfg, include_core=False, provider="claude-code"):
    """Dry calculation: what to add/update/delete. Doesn't write anything.

    Returns dict: {add, update, managed_drift, remove, keep, conflicts,
    skills_path, entries}. ``managed_drift`` takes precedence over source staleness:
    manual editing installed SKILL.md does not become normal update.
    - add:    name's new managed-skills
    - update: name's managed-skills with divergent sha256 (or a missing file)
    - remove: name's managed-skills from lock, which are no longer in the config
    - keep:   managed-skills unchanged
    - conflicts: name's from add, whose path is occupied by someone else's skill (not managed) — symlink/
                 directory/file that we did not install. sync without force skips them.
    Aliens (managed!=true) records are NOT included in the deletion calculation."""
    entries, skipped = resolve_skillset(env, cfg, include_core=include_core)
    skills_path = cfg.get("skills_path") or DEFAULT_SKILLS_PATH
    dest_root = Path(target) / skills_path
    lock = load_lock(target)
    lock_problem = _lock_problem(target)
    locked = (lock.get("skills", {}) if provider == "claude-code"
              else lock.get("providers", {}).get(provider, {}))

    desired = {e["name"]: e for e in entries}
    managed_locked = {n: e for n, e in locked.items() if e.get("managed")}

    add, update, managed_drift, keep, conflicts, conflicts_likely_ours = [], [], [], [], [], []
    drift_hashes = {}
    for name, entry in desired.items():
        dst = dest_root / name
        prev = managed_locked.get(name)
        if prev is None:
            # new to us; if the path is occupied by someone else (not managed) — conflict. NOT auto-
            # adopt even if there is a match sha256 (V-6): conscious "manual cleaning
            # lock + live folder" (test_manual_lock_cleanup_*) also gives the exact
            # content match, but requires --force — fuse against
            # accidental absorption of someone else's. We distinguish in the MESSAGE (see sync_skillset):
            # matching sha256 → rather interrupted past sync (--force is safe),
            # mismatched → really someone else's skill.
            if dst.is_symlink() or dst.exists():
                conflicts.append(name)
                if not dst.is_symlink() and dst.is_dir() \
                        and _dir_sha256(dst) == entry["sha256"]:
                    conflicts_likely_ours.append(name)
            else:
                add.append(name)
        elif prev.get("installed_path") and prev["installed_path"] != f"{skills_path}/{name}":
            # A configured target-path move is a managed relocation, not drift in
            # the old managed bytes. The old location is pruned via ``relocated``.
            add.append(name)
        elif not dst.is_dir() or dst.is_symlink():
            managed_drift.append(name)
            drift_hashes[name] = {
                "observed": _hash_label(""),
                "expected": _hash_label(prev.get("sha256", "")),
                "source": _hash_label(entry["sha256"]),
            }
        elif _dir_sha256(dst) != prev.get("sha256"):
            # Managed bytes are classified before canonical source/content changes:
            # ordinary sync must never overwrite a local edit incidentally.
            managed_drift.append(name)
            drift_hashes[name] = {
                "observed": _hash_label(_dir_sha256(dst)),
                "expected": _hash_label(prev.get("sha256", "")),
                "source": _hash_label(entry["sha256"]),
            }
        elif prev.get("sha256") != entry["sha256"]:
            update.append(name)
        elif (prev.get("content_sha256")
              and prev.get("content_sha256") != entry.get("content_sha256", "")):
            # drift in snippets/references with unchanged SKILL.md. Guard for presence
            # key in the lock → old locks (without content_sha256) do not give false update.
            update.append(name)
        else:
            keep.append(name)
    remove = [n for n in managed_locked if n not in desired]
    # V-9: managed-entry whose installed_path (lock) does NOT match CURRENT skills_path
    # (changed the config skills_path) — a copy along the old path will be orphaned if it is not
    # pruned separately from the usual remove (remove only hits «dropped out of the config»,
    # but this skill may remain desired — is just moving). {name: old rel-path}.
    relocated = {n: e["installed_path"] for n, e in managed_locked.items()
                if e.get("installed_path") and e["installed_path"] != f"{skills_path}/{n}"}
    return {
        "add": sorted(add), "update": sorted(update),
        "managed_drift": sorted(managed_drift),
        "drift_hashes": drift_hashes,
        "remove": sorted(remove), "keep": sorted(keep),
        "conflicts": sorted(conflicts),
        "conflicts_likely_ours": sorted(conflicts_likely_ours),
        "relocated": relocated,
        "skipped": skipped, "skills_path": skills_path,
        "entries": entries, "dest_root": dest_root,
        "provenance_invalid": lock_problem,
    }


def _plan_for_sync(env, target, cfg, **kwargs):
    # plan_sync is looked up at call time, so a replaced plan_sync is honoured.
    return plan_sync(env, target, cfg, **kwargs)


# The sync itself applies a plan (aicore.delivery.materialize); planning stays here, because it reads
# the skill library and the selection rules. Without an explicit ``plan`` the sync plans through plan_sync.
sync_skillset = functools.partial(_sync_skillset, planner=_plan_for_sync)


# --- config materialization (common for init and do_sync) ------------------------
def materialize_skillset_config(env, target, opts, dry=False, force=False, quiet=False):
    """Return config vendor-mode; create `.swissknifeman/config.json` from
    project profile, if it does not already exist (force=True — recreate from autodetect).

    Existing curated config is respected (force=False → read as is, not
    grind). SINGLE materialization point for `cmd_init` and `do_sync` — to
    the default set did not disperse between «create config» and «sync».
    Returns (cfg, profile_name, created): created=True, if the file is written."""
    cfg_path = skillset_config_path(target)
    if cfg_path.is_file() and not force:
        cfg = load_skillset_config(target)
        return cfg, (cfg.get("project_type") or ""), False
    legacy = load_config(env, target)
    buckets, profile_name, _psrc, source, _meta = resolve_selection(
        env, target, legacy, opts.get("profile", ""), [])
    cfg = {"version": LOCK_VERSION, "mode": "vendor", "agent": "claude",
           "buckets": list(buckets), "include": [], "exclude": []}
    if not dry:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(cfg_path, cfg, version=LOCK_VERSION)
    if not quiet:
        print(("[dry-run] " if dry else "")
              + f"config vendor-mode: {CONFIG_DIR}/{CONFIG_FILE} "
              f"(mode=vendor, buckets: {' '.join(buckets) or '-'})")
    if source == "autodetect-fallback" and not quiet:
        print("⚠ project type not recognized - MINIMUM kernel materialized;\n"
              "  for optimal dialing, specify the profile: --profile <type>")
    return cfg, profile_name, True


# --- integrate/onboard entry (vendor-channel «publish to repo») -------------
def _do_sync_provider(env, target, opts, register=True, plan=None):
    """Vendor-channel via sync: «publish» skills physically in .claude/skills/.

    This is the way to go for projects that outsource to third party developers WITHOUT access to
    registry swissknifeman: skill files are committed to the project repo (unlike
    connect, where skills live as plugins in the registry). Materializes
    .swissknifeman/config.json from the project profile, if there is no config yet; already
    existing curated config is respected (do not grind). Parity with
    connect/do_vendor: permissions-presets, hub, registration (channel=vendor)."""
    dry = opts.get("dry_run", False)
    force = opts.get("force", False)
    repair = opts.get("repair", False)
    no_core = opts.get("no_core", False)

    provider = opts.get("provider", "claude-code")
    cfg, profile_name, _created = materialize_skillset_config(
        env, target, opts, dry=dry)
    if provider == "codex":
        cfg = {**cfg, "skills_path": ".agents/skills", "agent": "codex"}

    plan = sync_skillset(env, target, cfg, dry_run=dry, force=force, repair=repair,
                         include_core=not no_core, provider=provider, plan=plan)
    n_add, n_upd, _n_repl, n_skip = _sync_report_counts(plan, dry, force)
    print(("[dry-run] " if dry else "")
          + f"sync: +{n_add} ~{n_upd} "
          f"-{len(plan['remove'])} ={len(plan['keep'])} "
          f"(skills_path: {plan['skills_path']})")
    if plan["conflicts"] and not force:
        print(f"  conflicts (alien, missed): {', '.join(plan['conflicts'])} "
              "— --force to replace")
    if plan["skipped"]:
        print(f"  missing (not in the registry): {', '.join(plan['skipped'])}")
    if n_skip:
        print(f"  OMITTED when copying ({n_skip}): "
              f"{', '.join(plan['skip_copy'])} — see warnings above, "
              f"sync is NOT completed for them")
        die(f"SPUB_OWNERSHIP_CONFLICT: provider {provider} vendor apply incomplete; "
            "repair: resolve the target conflict and rerun `skiller sync`")
    for evidence in plan.get("repair_evidence", []):
        print(f"  repair {evidence['name']}: observed={evidence['observed']} "
              f"expected={evidence['expected']} source={evidence['source']}")

    # permissions-presets (deny garbage + allow stack) — parity with connect/do_vendor
    if provider == "claude-code" and not opts.get("no_permissions"):
        apply_permissions(env, target, dry_run=dry)

    if opts.get("hub") and not dry:
        generate_hub(env, target)

    record = {
        "path": str(target),
        "channel": "vendor",
        "profile": profile_name,
        "agent": "codex" if provider == "codex" else "claude",
        "skills_path": plan["skills_path"],
        "provider": provider,
        "hub": opts.get("hub") or hub_artifacts_exist(target),
    }
    if plan.get("repair_evidence"):
        record["repair"] = plan["repair_evidence"]
    if register and not dry:
        upsert_project(env, record)
    return record


def do_sync(env, target, opts, register=True):
    """Build every selected provider plan before the first managed write."""
    from .config import load_config
    from .publication import build_vendor_distribution_plan
    config = load_config(env, target)
    # Derive a missing vendor config in memory first.  An aggregate ownership,
    # drift or provenance refusal must not leave config materialisation behind.
    preflight_cfg, _profile, _created = materialize_skillset_config(
        env, target, opts, dry=True, quiet=True)
    paths = build_vendor_distribution_plan(
        config, target, project_id=target.name,
        claude_path=preflight_cfg.get("skills_path") or DEFAULT_SKILLS_PATH,
        codex_path=".agents/skills")
    provider_ids = opts.get("provider_ids")
    if provider_ids is not None:
        provider_ids = frozenset(provider_ids)
        paths = tuple(path for path in paths if path.provider_id in provider_ids)
    lock_problem = _lock_problem(target)
    if lock_problem:
        providers = ", ".join(descriptor.provider_id for descriptor in paths) or "none"
        targets = ", ".join(descriptor.target.relative_to(target).as_posix()
                            for descriptor in paths) or "-"
        die(f"SPUB_OWNERSHIP_CONFLICT: provider {providers} channel vendor "
            f"target {targets} has invalid skills-lock provenance ({lock_problem}); "
            "repair: restore a valid lock backup")
    planned = []
    for descriptor in paths:
        provider = descriptor.provider_id
        provider_cfg = ({**preflight_cfg, "skills_path": ".agents/skills", "agent": "codex"}
                        if provider == "codex" else preflight_cfg)
        # The immutable copy plan is calculated for every selected provider
        # before applying any of them.  A later provider conflict therefore
        # cannot turn the earlier provider into a misleading partial success.
        planned.append((provider, plan_sync(
            env, target, provider_cfg, include_core=not opts.get("no_core", False),
            provider=provider)))

    # A selected provider's unmanaged target is an aggregate preflight failure:
    # applying Claude first and silently skipping Codex would report a misleading
    # dual-provider success.  ``--force`` remains the explicit, existing escape
    # hatch for the owner of that target.
    for provider, plan in planned:
        if plan.get("provenance_invalid"):
            die(f"SPUB_OWNERSHIP_CONFLICT: provider {provider} channel vendor "
                f"target {plan['skills_path']} has invalid skills-lock provenance "
                f"({plan['provenance_invalid']}); repair: restore a valid lock backup")
        if plan["conflicts"] and not opts.get("force", False):
            conflicts = ", ".join(plan["conflicts"])
            die(f"SPUB_OWNERSHIP_CONFLICT: provider {provider} channel vendor "
                f"target {plan['skills_path']} has unmanaged conflicts: {conflicts}; "
                "repair: resolve the target conflict or rerun `skiller sync --force`")
        if plan.get("managed_drift") and not opts.get("repair", False):
            drifts = ", ".join(plan["managed_drift"])
            die(f"SPUB_OWNERSHIP_CONFLICT: provider {provider} channel vendor "
                f"target {plan['skills_path']} has managed-drift: {drifts}; "
                "repair: rerun `skiller sync --repair`")

    # Only a clean aggregate plan is allowed to materialise the project config.
    base_cfg, _profile, _created = materialize_skillset_config(
        env, target, opts, dry=opts.get("dry_run", False))
    records = [_do_sync_provider(env, target, {**opts, "provider": provider},
                                 register=register, plan=plan)
               for provider, plan in planned]
    return records[0] if len(records) == 1 else {"providers": records}


# --- CLI ----------------------------------------------------------------------
def cmd_init(env, argv):
    """Create `.swissknifeman/config.json` (mode=vendor) — without copying skills.

    Front, idempotent door «give me the config»: project type autodetect +
    profile → buckets. Copying does `skiller sync`. Previously config
    only materialized as a side effect `sync`/`integrate`."""
    opts = parse_flags(argv, {"--target": "str", "--profile": "str",
                              "--force": "bool", "--dry-run": "bool"})
    if opts["help"]:
        print("skiller init [--target DIR] [--profile TYPE] [--force] [--dry-run]\n"
              "  Creates .swissknifeman/config.json (mode=vendor) from autodetect "
              "project type and profile -\n"
              "  WITHOUT copying skills (does this skiller sync). Existing "
              "the config is not deleted without --force.")
        return
    target, via = resolve_target(env, opts, allow_home_confirm=True)
    cfg_path = skillset_config_path(target)
    if cfg_path.is_file() and not opts["force"]:
        print(f"✓ {CONFIG_DIR}/{CONFIG_FILE} already exists ({via}) — I don't touch "
              "(--force recreates). Next: skiller sync")
        return
    _cfg, profile_name, _created = materialize_skillset_config(
        env, target, opts, dry=opts["dry_run"], force=True)
    if not opts["dry_run"]:
        print(f"  profile: {profile_name or '-'}. Edit "
              "include/buckets/exclude and apply: skiller sync")


def cmd_sync(env, argv):
    opts = parse_flags(argv, {"--target": "str", "--dry-run": "bool",
                              "--force": "bool", "--hub": "bool",
                              "--no-hub": "bool", "--no-core": "bool",
                              "--repair": "bool"})
    if opts["help"]:
        print("skiller sync [--target DIR] [--dry-run] [--force] [--repair] "
              "[--hub] [--no-hub] [--no-core]\n"
              "  Applies .swissknifeman/config.json (mode=vendor): copies "
              "skills from the library to the project, writes skills-lock.json (managed),\n"
              "  manifest .swissknifeman-manifest.json and deletes the retired ones "
              "managed-skills. Doesn't touch other people's skills (--force grinds\n"
              "  occupied by someone else's path with a version from the library); --repair restores\n"
              "  confirmed only managed-drift with recoverable pre-image. CORE-skills "
              "are distributed by default (--no-core disables). Skill Index\n"
              "  (managed-block CLAUDE.md / .ai/guidelines) is updated if it "
              "is already in the project or passed --hub; --no-hub disables.")
        return
    target, via = resolve_target(env, opts, allow_home_confirm=True)
    cfg = load_skillset_config(target)
    if cfg is None:
        die(f"{skillset_config_path(target)} not found - create a config "
            "vendor-mode (mode=vendor, include/buckets/exclude)")

    # Skills index at the root of the project: catching up with behavior vendor — update,
    # if the hub already exists or is explicitly requested. --no-hub overrides autodetection.
    want_hub = opts["hub"] or (hub_artifacts_exist(target)
                               and not opts["no_hub"])
    do_sync(env, target, {**opts, "hub": want_hub})
