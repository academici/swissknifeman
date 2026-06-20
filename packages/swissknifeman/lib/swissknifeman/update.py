"""update — обновить подключение/вендоринг проекта (диск — источник истины)."""
import json
from pathlib import Path

from .common import AGENT_DEFAULTS, MANIFEST, MARKETPLACE, die, parse_flags, warn
from .config import load_config, resolve_target
from .connect import do_connect
from .hub import hub_artifacts_exist
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
    vendor_path = detect_vendor_path(target, config)
    records = {r["channel"]: r for r in db_records(env, target)}

    if not mk_file and not vendor_path:
        if records:
            warn(f"{target}: записан в projects.json, но маркеры подключения "
                 f"не найдены — забыть: swissknifeman list --prune")
        else:
            die(f"{target} не подключён — выполните 'swissknifeman connect' "
                f"(Claude Code) или 'swissknifeman vendor' (другие агенты)")
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
        do_connect(env, target, opts, fix_path_drift=True)
        print_registry_state(env)
    if vendor_path:
        rec = records.get("vendor", {})
        manifest = {}
        mf = target / vendor_path / MANIFEST
        if mf.is_file():
            manifest = json.loads(mf.read_text(encoding="utf-8"))
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
        print("swissknifeman update [--all] [--dry-run]")
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
                     f"(забыть: swissknifeman list --prune)")
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
