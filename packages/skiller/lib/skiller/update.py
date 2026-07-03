"""update — обновить подключение/вендоринг проекта (диск — источник истины)."""
import json
from pathlib import Path

from .common import AGENT_DEFAULTS, MANIFEST, MARKETPLACE, die, parse_flags, warn
from .config import load_config, resolve_target
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


def detect_vendor_path(target, config):
    candidates = []
    if config.get("skills_path"):
        candidates.append(config["skills_path"])
    candidates += [p for p in AGENT_DEFAULTS.values() if p not in candidates]
    for p in candidates:
        if (target / p / MANIFEST).is_file():
            return p
    return None


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


def update_one(env, target, dry_run=False):
    config = load_config(env, target)
    mk_file = detect_marketplace_file(target)
    # sync-канал (.swissknifeman/config.json) владеет тем же .swissknifeman-manifest.json,
    # что и legacy vendor — поэтому при наличии sync-конфига обновляем sync'ом (он
    # уважает skill-granular include/exclude), а detect_vendor_path не трогаем.
    sync_cfg = load_skillset_config(target)
    vendor_path = None if sync_cfg else detect_vendor_path(target, config)
    records = {r["channel"]: r for r in db_records(env, target)}

    if not mk_file and not sync_cfg and not vendor_path:
        if records:
            warn(f"{target}: записан в projects.json, но маркеры подключения "
                 f"не найдены — забыть: skiller list --prune")
        else:
            die(f"{target} не подключён — выполните 'skiller connect' "
                f"(Claude Code) или 'skiller vendor' (другие агенты)")
        return False

    ok = True
    if mk_file:
        rec = records.get("marketplace", {})
        if not rec:
            print(f"NOTE: {target} не был в projects.json — регистрирую (adopt)")
        opts = replay_opts(rec)
        opts["file"] = mk_file
        opts["dry_run"] = dry_run
        opts["hub"] = bool(rec.get("hub")) or hub_artifacts_exist(target)
        print(f"--- update (marketplace): {target} ---")
        # P7.5: бакет слит (alias) — старое имя ещё включено у проекта → одна строка,
        # без нагнетания (сам update ничего не переключает, только подсказывает).
        for hint in alias_migration_hints(
                load_bucket_aliases(env), enabled_marketplace_plugins(target, mk_file)):
            print(f"Подсказка: {hint}")
        do_connect(env, target, opts, fix_path_drift=True)
        print_registry_state(env)
    if sync_cfg:
        # канонический Claude-канал: пере-sync из .swissknifeman/config.json (skill-granular)
        rec = records.get("vendor", {})
        if not rec:
            print(f"NOTE: {target} не был в projects.json — регистрирую (adopt)")
        print(f"--- update (sync): {target} ---")
        do_sync(env, target, {"dry_run": dry_run,
                              "hub": bool(rec.get("hub")) or hub_artifacts_exist(target)})
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
        if not config.get("agent"):
            agent = rec.get("agent") or manifest.get("agent") or ""
            if agent:
                opts["agent"] = agent
        if not config.get("skills_path"):
            opts["skills_path"] = vendor_path
        if rec.get("exclude"):
            opts["exclude"] = ",".join(rec["exclude"])
        if not opts.get("profile") and not opts.get("buckets") \
                and not config.get("buckets") and not config.get("project_type") \
                and manifest.get("profile"):
            opts["profile"] = manifest["profile"]
        opts["dry_run"] = dry_run
        opts["hub"] = bool(rec.get("hub")) or hub_artifacts_exist(target)
        print(f"--- update (vendor): {target} ---")
        do_vendor(env, target, opts)
    return ok


def cmd_update(env, argv):
    opts = parse_flags(argv, {"--target": "str", "--all": "bool",
                              "--dry-run": "bool"})
    if opts["help"]:
        print("skiller update [--all] [--dry-run]")
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
                update_one(env, target, dry_run=opts["dry_run"])
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
    update_one(env, target, dry_run=opts["dry_run"])
