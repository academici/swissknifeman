"""update — обновить подключение/вендоринг проекта (диск — источник истины)."""
import json
import shutil
import uuid
import re
from pathlib import Path

from core import atomic_write_text
from core.provider.lock import _contained_target, _writer_guard

from .common import AGENT_DEFAULTS, MANIFEST, MARKETPLACE, die, parse_flags, warn
from .config import ProjectConfig, load_config, resolve_target
from .connect import do_connect
from .hub import hub_artifacts_exist
from .registry import alias_migration_hints, load_bucket_aliases
from .skillset import do_sync, load_skillset_config
from .state import db_records, load_db, print_registry_state
from .vendor import do_vendor


def detect_marketplace_file(target):
    for fname in ("settings.local.json", "settings.json"):
        f = target / ".claude" / fname
        if f.is_file():
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if MARKETPLACE in s.get("extraKnownMarketplaces", {}):
                return fname
    return None


def detect_codex_marketplace(target):
    """The repository-local native Codex marketplace marker (no global state)."""
    marker = target / ".agents" / "plugins" / "marketplace.json"
    return marker if marker.is_file() else None


def detect_codex_skill_links(target):
    """Marker for the CLI-effective Codex project projection."""
    marker = target / ".agents" / ".swissknifeman-codex-links.json"
    return marker if marker.is_file() else None


def adopt_codex_provider_config(target, dry_run=False, plugins=None):
    """Opt an existing SKM project into the explicit three-provider contract.

    Legacy projects resolve to Claude Code only by compatibility default.  Codex
    therefore never receives its generated, project-contained marketplace bundle
    until the project declares it.  This migration is intentionally explicit at
    the CLI boundary and preserves every unrelated project setting.
    """
    target = Path(target)
    config_path = target / ".swissknife.json"
    data = {}
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            die(f"{config_path}: invalid JSON: {exc}")
    if not isinstance(data, dict):
        die(f"{config_path}: корень должен быть JSON-object")
    providers = data.get("providers")
    if providers is None:
        providers = {}
        data["providers"] = providers
    if not isinstance(providers, dict):
        die(f"{config_path}: providers должен быть JSON-object")
    selection = providers.setdefault("selection", {})
    if not isinstance(selection, dict):
        die(f"{config_path}: providers.selection должен быть JSON-object")
    changed = False
    if providers.get("contract_version") != "1.0.0":
        providers["contract_version"] = "1.0.0"
        changed = True
    for provider in ("claude-code", "codex", "cursor"):
        value = selection.get(provider)
        if value is None:
            selection[provider] = {"enabled": True}
            changed = True
        elif not isinstance(value, dict):
            die(f"{config_path}: providers.selection.{provider} должен быть JSON-object")
    if (plugins is not None and "plugins" not in data and not data.get("buckets")
            and not data.get("project_type")):
        data["plugins"] = list(plugins)
        changed = True
    if not changed:
        return False
    if dry_run:
        print(f"[dry-run] adopt three-provider contract {config_path}")
        return True
    if config_path.exists():
        shutil.copy2(config_path, f"{config_path}.bak")
    atomic_write_text(config_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"adopt three-provider contract {config_path}")
    return True


def prune_legacy_task_runtime_link(env, target, dry_run=False):
    """Remove only the former per-project task runtime link.

    ``task`` is a plugin runtime.  Older bootstrap attempts created
    ``packages/task`` links in consumer repositories; that bypasses both provider
    adapters and makes a project accidentally depend on the hub checkout/cache.
    Recognise only the three historical SKM destinations, never a project-owned
    link with the same path.
    """
    legacy = Path(target) / "packages" / "task"
    if not legacy.is_symlink():
        return False
    try:
        destination = legacy.resolve(strict=True)
    except OSError:
        return False
    managed_roots = (
        env.root / "packages" / "task",
        env.home / ".claude" / "plugins" / "cache" / MARKETPLACE / "task",
        env.home / ".codex" / "plugins" / "cache" / MARKETPLACE / "task",
    )
    if not any(destination == root or root in destination.parents
               for root in managed_roots):
        return False
    if dry_run:
        print(f"[dry-run] remove legacy task runtime link {legacy}")
    else:
        legacy.unlink()
        print(f"remove legacy task runtime link {legacy}")
    return True


def retire_orphaned_codex_vendor_manifest(target, *, dry_run=False):
    """Archive a v1 Claude mirror marker only when every declared directory is gone."""
    target = Path(target)
    with _writer_guard(target):
        path = _contained_target(target, ".agents/skills/" + MANIFEST)
        if not path.is_file() or not detect_codex_marketplace(target):
            return False
        value = json.loads(path.read_text())
        records = value.get("skills")
        if value.get("version") != 1 or value.get("layout") != "flat" or value.get("agent") != "claude" or not isinstance(records, list) or not records:
            return False
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("flat_name"), str) or not record.get("source_path"):
                return False
            directory = _contained_target(target, ".agents/skills/" + record["flat_name"])
            if directory.exists():
                return False
        backup = _contained_target(target, ".swissknifeman/backups/orphaned-codex-vendor-" + uuid.uuid4().hex + ".json")
        if dry_run:
            print(f"[dry-run] archive orphaned vendor marker {path}")
        else:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, backup)
            print(f"archive orphaned vendor marker {path}; backup={backup}")
        return True


_CODEX_PHYSICAL_KEEP = frozenset({"ecosystem-mcp", "ecosystem-setup"})


def retire_orphan_codex_physical_skills(env, target, *, dry_run=False):
    """Archive manifest-less physical copies in ``.agents/skills`` when Codex marketplace is on.

    Leftovers from pre-contained-bundle connect: skills are served via
    ``.agents/plugins/marketplace.json``; physical SKILL.md trees duplicate listing budget.
    """
    target = Path(target)
    if not detect_codex_marketplace(target):
        return False
    skills_dir = target / ".agents" / "skills"
    if not skills_dir.is_dir():
        return False
    from core.provider.lock import LOCK_RELATIVE_PATH, parse_lock
    lock_path = _contained_target(target, LOCK_RELATIVE_PATH)
    owned = parse_lock(lock_path.read_bytes()).records if lock_path.is_file() else ()
    owned_prefixes = tuple(r.target_path for r in owned)
    targets = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith(".") or entry.name == MANIFEST:
            continue
        if entry.name in _CODEX_PHYSICAL_KEEP:
            continue
        if entry.is_symlink():
            continue
        if not entry.is_dir() or not (entry / "SKILL.md").is_file():
            continue
        rel = ".agents/skills/" + entry.name
        if any(op == rel or op.startswith(rel + "/") for op in owned_prefixes):
            continue
        targets.append(entry)
    if not targets:
        return False
    backup = _contained_target(target,
                               ".swissknifeman/backups/legacy-codex-physical-" + uuid.uuid4().hex)
    if dry_run:
        print(f"[dry-run] retire {len(targets)} orphan Codex physical skill dirs; "
              f"backup={backup}")
        return True
    backup.mkdir(parents=True, exist_ok=True)
    for directory in targets:
        shutil.move(directory, backup / directory.name)
    print(f"retire {len(targets)} orphan Codex physical skill dirs; backup={backup}")
    return True


def retire_legacy_codex_vendor(env, target, *, dry_run=False):
    """Explicit connector cleanup of manifest-declared copies, with reversible backup."""
    from core.provider.lock import LOCK_RELATIVE_PATH, parse_lock
    target = Path(target)
    with _writer_guard(target):
        path = _contained_target(target, ".agents/skills/" + MANIFEST)
        if not path.is_file() or not detect_codex_marketplace(target):
            return False
        value = json.loads(path.read_text())
        records = value.get("skills")
        if value.get("version") != 1 or value.get("layout") != "flat" or value.get("agent") not in ("claude", "codex") or not isinstance(records, list):
            raise ValueError("LEGACY_VENDOR_UNRECOGNIZED: cleanup requires the known v1 vendor manifest")
        lock_path = _contained_target(target, LOCK_RELATIVE_PATH)
        owned = parse_lock(lock_path.read_bytes()).records if lock_path.is_file() else ()
        targets = []
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("flat_name"), str) or not isinstance(record.get("source_path"), str):
                raise ValueError("LEGACY_VENDOR_UNRECOGNIZED: malformed record")
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", record["flat_name"]):
                raise ValueError("LEGACY_VENDOR_UNRECOGNIZED: unsafe target name")
            source = Path(record["source_path"])
            source = source if source.is_absolute() else env.root / source
            if not source.resolve().is_relative_to((env.root / "skills").resolve()):
                raise ValueError("LEGACY_VENDOR_UNRECOGNIZED: foreign source")
            relative = ".agents/skills/" + record["flat_name"]
            directory = _contained_target(target, relative)
            if any(r.target_path == relative or r.target_path.startswith(relative + "/") for r in owned):
                raise ValueError("LEGACY_VENDOR_FOREIGN_OWNER: preserve " + relative)
            if directory.exists():
                targets.append(directory)
        backup = _contained_target(target, ".swissknifeman/backups/legacy-codex-vendor-" + uuid.uuid4().hex)
        if not dry_run:
            backup.mkdir(parents=True, exist_ok=True)
            for directory in sorted(set(targets)):
                shutil.move(directory, backup / directory.name)
            shutil.move(path, backup / MANIFEST)
        print(f"{'[dry-run] ' if dry_run else ''}retire {len(set(targets))} legacy Codex vendor directories; backup={backup}")
        return True


def detect_vendor_path(target, config):
    config = ProjectConfig.coerce(config)  # исторические вызовы передают dict
    candidates = []
    if config.skills_path:
        candidates.append(config.skills_path)
    candidates += [p for p in AGENT_DEFAULTS.values() if p not in candidates]
    for p in candidates:
        if (target / p / MANIFEST).is_file():
            return p
    return None


def retire_legacy_codex_links(env, target, *, dry_run=False):
    """Retire declared links replaced by native skills or explicitly disabled locally.

    The marker owns link destinations, never the source directories. Modified
    links and files fail before mutation; unique local capabilities remain.
    """
    from .native_codex import native_inventory
    from .common import find_monorepo_root, parse_frontmatter
    from core.provider.lock import LOCK_RELATIVE_PATH, parse_lock
    target = Path(target)
    marker = target / ".agents/.swissknifeman-codex-links.json"
    if not marker.is_file():
        return False
    inventory = native_inventory(env, target)
    if not inventory["ok"]:
        raise ValueError("CODEX_DISCOVERY_UNKNOWN: cannot retire skill links without native replacement evidence")
    with _writer_guard(target):
        marker = _contained_target(target, ".agents/.swissknifeman-codex-links.json")
        original = marker.read_text()
        value = json.loads(original)
        links = value.get("links")
        if value.get("version") != 1 or not isinstance(links, dict):
            raise ValueError("LEGACY_LINKS_UNRECOGNIZED: expected v1 links map")
        disabled = set()
        selection_path = _contained_target(target, ".codex/config.toml")
        if selection_path.is_file():
            from .native_codex import _read
            _, selection = _read(selection_path)
            effective = {Path(row["path"]).resolve(): row.get("enabled")
                         for row in selection.get("skills", {}).get("config", [])
                         if isinstance(row.get("path"), str) and Path(row["path"]).is_absolute()}
            disabled = {path for path, enabled in effective.items() if enabled is False}
        lock_path = _contained_target(target, LOCK_RELATIVE_PATH)
        owned = parse_lock(lock_path.read_bytes()).records if lock_path.is_file() else ()
        repo = find_monorepo_root(env.root)
        allowed = [env.root / "skills", env.root / "adapters/codex"]
        if repo is not None:
            allowed.append(Path(repo) / "packages/task/adapters/codex/skills")
        pending = []
        for name, destination in links.items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or not isinstance(destination, str):
                raise ValueError("LEGACY_LINKS_UNRECOGNIZED: unsafe link declaration")
            source = Path(destination)
            if not source.is_absolute() or not any(source.resolve().is_relative_to(p.resolve()) for p in allowed):
                raise ValueError("LEGACY_LINKS_UNRECOGNIZED: source outside owned skill roots")
            # Check the parent, not the symlink target: the target is intentionally external.
            directory = _contained_target(target, ".agents/skills")
            link = directory / name
            if not link.is_symlink() or link.resolve() != source.resolve():
                raise ValueError("LEGACY_LINK_MODIFIED: preserve " + str(link))
            md = link / "SKILL.md"
            if not md.is_file():
                continue
            identity = parse_frontmatter(md).get("name", name)
            explicitly_disabled = md.resolve() in disabled
            if explicitly_disabled or identity in inventory["native_names"]:
                # A same-name cache entry can be stale. Preserve every source file,
                # including referenced instructions, before retiring its local carrier.
                replacements = [Path(p).parent for p in inventory.get("paths", {}).get(identity, [])
                                if "/plugins/cache/swissknifeman/" in str(p)]
                files = [p for p in source.rglob("*") if p.is_file()]
                equivalent = any(all((candidate / p.relative_to(source)).is_file()
                                     and (candidate / p.relative_to(source)).read_bytes() == p.read_bytes()
                                     for p in files) for candidate in replacements)
                if not explicitly_disabled and not equivalent:
                    print("preserve non-equivalent native replacement: " + name)
                    continue
                relative = ".agents/skills/" + name
                if any(r.target_path == relative or r.target_path.startswith(relative + "/") for r in owned):
                    raise ValueError("LEGACY_LINK_FOREIGN_OWNER: preserve " + relative)
                pending.append((name, link))
        if not pending:
            return False
        backup = _contained_target(target, ".swissknifeman/backups/legacy-codex-links-" + uuid.uuid4().hex)
        if not dry_run:
            backup.mkdir(parents=True)
            (backup / marker.name).write_text(original)
            for name, link in pending:
                link.rename(backup / name)
            retained = dict(value)
            retired = {name for name, _link in pending}
            retained["links"] = {k:v for k,v in links.items() if k not in retired}
            atomic_write_text(marker, json.dumps(retained, ensure_ascii=False, indent=2) + "\n")
        print(f"{'[dry-run] ' if dry_run else ''}retire {len(pending)} replaced/disabled Codex skill links; backup={backup}")
        return True


def _equivalent_skill_tree(source, candidate):
    """Compare skill content while ignoring non-runtime import provenance."""
    def files(root):
        return {
            path.relative_to(root): path
            for path in root.rglob("*")
            if path.is_file() and path.name != "upstream.json"
        }

    source_files = files(source)
    candidate_files = files(candidate)
    return (source_files.keys() == candidate_files.keys()
            and all(path.read_bytes() == candidate_files[relative].read_bytes()
                    for relative, path in source_files.items()))


def retire_equivalent_codex_skill_links(env, target, *, dry_run=False):
    """Archive unowned local skill links only when a native SKM copy is identical.

    Some pre-native projects linked their own ``.ai/skills`` trees into
    ``.agents/skills`` without the generated ownership marker.  The link is a
    redundant Codex discovery carrier when every runtime skill file is already
    supplied by an active SKM plugin.  The source tree remains untouched and
    the link is recoverable from the backup.
    """
    from .common import parse_frontmatter
    from .native_codex import native_inventory
    from core.provider.lock import LOCK_RELATIVE_PATH, parse_lock

    target = Path(target)
    inventory = native_inventory(env, target)
    if not inventory["ok"]:
        raise ValueError("CODEX_DISCOVERY_UNKNOWN: cannot retire equivalent links without native inventory")
    skills_dir = target / ".agents" / "skills"
    if not skills_dir.is_dir():
        return False
    with _writer_guard(target):
        lock_path = _contained_target(target, LOCK_RELATIVE_PATH)
        owned = parse_lock(lock_path.read_bytes()).records if lock_path.is_file() else ()
        pending = []
        for link in sorted(skills_dir.iterdir()):
            if not link.is_symlink() or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", link.name):
                continue
            try:
                source = link.resolve(strict=True)
            except OSError:
                continue
            md = source / "SKILL.md"
            if not source.is_dir() or not md.is_file():
                continue
            identity = parse_frontmatter(md).get("name", link.name)
            replacements = [Path(path).parent for path in inventory.get("paths", {}).get(identity, [])
                            if "/plugins/cache/swissknifeman/" in str(path)]
            if not any(_equivalent_skill_tree(source, candidate) for candidate in replacements):
                continue
            relative = ".agents/skills/" + link.name
            if any(record.target_path == relative or record.target_path.startswith(relative + "/")
                   for record in owned):
                continue
            pending.append(link)
        if not pending:
            return False
        backup = _contained_target(target,
                                   ".swissknifeman/backups/legacy-codex-equivalent-links-" + uuid.uuid4().hex)
        if not dry_run:
            backup.mkdir(parents=True)
            for link in pending:
                link.rename(backup / link.name)
        print(f"{'[dry-run] ' if dry_run else ''}retire {len(pending)} equivalent Codex skill links; backup={backup}")
        return True


def enabled_marketplace_plugins(target, mk_file):
    """Активные (True) плагины marketplace-канала из settings-файла — имена без
    '@<marketplace>'. Fail-safe: битый/пропавший файл → [] (гонка/порча между
    detect_marketplace_file и этим чтением не должна ронять update)."""
    f = target / ".claude" / mk_file
    try:
        s = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [k.split("@")[0] for k, v in s.get("enabledPlugins", {}).items()
            if k.endswith(f"@{MARKETPLACE}") and v]


def replay_opts(record):
    """projects.json record -> flags for do_connect/do_vendor.
    Explicit user choices (flag/plugins/buckets) are replayed; autodetect and
    config sources re-resolve from disk."""
    opts = {}
    src = record.get("profile_source", "autodetect")
    if src == "flag" and record.get("profile"):
        opts["profile"] = record["profile"]
    elif src == "plugins" and record.get("plugins"):
        opts["plugins"] = ",".join(record["plugins"])
    elif src == "buckets" and record.get("buckets"):
        opts["buckets"] = ",".join(record["buckets"])
    return opts


def update_one(env, target, dry_run=False, adopt_codex=False):
    records = {}
    for record in db_records(env, target):
        current = records.get(record["channel"])
        # Marketplace semantics (profile/plugins) live on the Claude record;
        # the Codex projection record intentionally carries only its target.
        if current is None or (record.get("plugins") and not current.get("plugins")):
            records[record["channel"]] = record
    if adopt_codex:
        record_plugins = records.get("marketplace", {}).get("plugins")
        adopt_codex_provider_config(target, dry_run=dry_run, plugins=record_plugins)
    config = load_config(env, target)
    mk_file = detect_marketplace_file(target)
    codex_marketplace = detect_codex_marketplace(target)
    codex_links = detect_codex_skill_links(target)
    # sync-канал (.swissknifeman/config.json) владеет тем же .swissknifeman-manifest.json,
    # что и legacy vendor — поэтому при наличии sync-конфига обновляем sync'ом (он
    # уважает skill-granular include/exclude), а detect_vendor_path не трогаем.
    sync_cfg = load_skillset_config(target)
    vendor_path = None if sync_cfg else detect_vendor_path(target, config)

    if not mk_file and not codex_marketplace and not codex_links and not sync_cfg and not vendor_path:
        if records:
            warn(f"{target}: записан в projects.json, но маркеры подключения "
                 f"не найдены — забыть: skiller list --prune")
        else:
            die(f"{target} не подключён — выполните 'skiller connect' "
                f"(Claude Code) или 'skiller vendor' (другие агенты)")
        return False

    # Migration only after a genuine SKM marker proved ownership of the project.
    # Do not use a consumer-local task copy as a compatibility fallback: both
    # Claude and Codex resolve this runtime from their installed plugin.
    prune_legacy_task_runtime_link(env, target, dry_run=dry_run)

    ok = True
    if mk_file or codex_marketplace or codex_links:
        rec = records.get("marketplace", {})
        if not rec:
            print(f"NOTE: {target} не был в projects.json — регистрирую (adopt)")
        opts = replay_opts(rec)
        if mk_file:
            opts["file"] = mk_file
        opts["dry_run"] = dry_run
        opts["hub"] = bool(rec.get("hub")) or hub_artifacts_exist(target)
        print(f"--- update (marketplace): {target} ---")
        # бакет слит (alias) — старое имя ещё включено у проекта → одна строка,
        # без нагнетания (сам update ничего не переключает, только подсказывает).
        if mk_file:
            for hint in alias_migration_hints(
                    load_bucket_aliases(env), enabled_marketplace_plugins(target, mk_file)):
                print(f"Подсказка: {hint}")
        do_connect(env, target, opts, fix_path_drift=True)
        # A first dual-provider connect just created the contained Codex
        # marketplace. Re-detect it before the sync branch below: otherwise the
        # same update incorrectly tries to deploy Codex once more through the
        # legacy vendor path and raises a false ownership conflict.
        codex_marketplace = detect_codex_marketplace(target)
        codex_links = detect_codex_skill_links(target)
        print_registry_state(env)
    if sync_cfg:
        # канонический Claude-канал: пере-sync из .swissknifeman/config.json (skill-granular)
        rec = records.get("vendor", {})
        if not rec:
            print(f"NOTE: {target} не был в projects.json — регистрирую (adopt)")
        print(f"--- update (sync): {target} ---")
        sync_opts = {
            "dry_run": dry_run,
            "hub": bool(rec.get("hub")) or hub_artifacts_exist(target),
        }
        if codex_marketplace or codex_links:
            # A Codex connect projection owns `.agents/skills`; keep the
            # independent Claude vendor channel out of that target.
            sync_opts["provider_ids"] = ("claude-code",)
        do_sync(env, target, sync_opts)
    elif vendor_path:
        rec = records.get("vendor", {})
        manifest = {}
        mf = target / vendor_path / MANIFEST
        if mf.is_file():
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                # Битый манифест — деградация, не крах: раньше необёрнутый json.loads
                # ронял необработанным исключением ВЕСЬ `update --all` (cmd_update ловит
                # только SystemExit) на первом же проекте с битым манифестом (аудит U-1).
                # manifest={} — agent/profile просто возьмутся из других источников
                # precedence (config/projects.json record), как для проекта без манифеста.
                warn(f"{mf}: битый JSON манифеста — игнорирую (agent/profile "
                     f"возьмутся из .swissknife.json/projects.json, если заданы): {e}")
        if not rec:
            print(f"NOTE: {target} не был в projects.json — регистрирую (adopt)")
        opts = replay_opts(rec)
        # precedence: .swissknife.json > projects.json record > manifest
        if not config.agent:
            agent = rec.get("agent") or manifest.get("agent") or ""
            if agent:
                opts["agent"] = agent
        if not config.skills_path:
            opts["skills_path"] = vendor_path
        if rec.get("exclude"):
            opts["exclude"] = ",".join(rec["exclude"])
        if not opts.get("profile") and not opts.get("buckets") \
                and not config.buckets and not config.project_type \
                and manifest.get("profile"):
            opts["profile"] = manifest["profile"]
        opts["dry_run"] = dry_run
        opts["hub"] = bool(rec.get("hub")) or hub_artifacts_exist(target)
        print(f"--- update (vendor): {target} ---")
        do_vendor(env, target, opts)
    retire_orphaned_codex_vendor_manifest(target, dry_run=dry_run)
    return ok


def cmd_update(env, argv):
    opts = parse_flags(argv, {"--target": "str", "--all": "bool",
                              "--dry-run": "bool", "--adopt-codex": "bool"})
    if opts["help"]:
        print("skiller update [--all] [--dry-run] [--adopt-codex]")
        return
    if opts["all"]:
        db = load_db(env)
        seen, results = set(), []
        for rec in db["projects"]:
            path = rec["path"]
            if path in seen:
                continue
            seen.add(path)
            target = Path(path)
            if not target.is_dir():
                warn(f"{path}: каталог не найден — пропускаю "
                     f"(забыть: skiller list --prune)")
                results.append((path, "missing"))
                continue
            if target.resolve() == env.root.resolve():
                continue
            try:
                update_one(env, target, dry_run=opts["dry_run"],
                           adopt_codex=opts["adopt_codex"])
                results.append((path, "ok"))
            except SystemExit:
                results.append((path, "failed"))
        print("\n--- итог ---")
        for path, state in results:
            print(f"  {state:8} {path}")
        if any(s == "failed" for _, s in results):
            import sys
            sys.exit(1)
        return
    target, _ = resolve_target(env, opts)
    update_one(env, target, dry_run=opts["dry_run"],
               adopt_codex=opts["adopt_codex"])
