"""connect — канал plugin marketplace Claude Code."""
import json
import os
import shutil

from .common import AGENT_DEFAULTS, MANIFEST, MARKETPLACE, die, parse_flags
from .config import all_buckets, load_config, resolve_selection, resolve_target
from .hub import generate_hub, hub_artifacts_exist
from .state import print_registry_state, upsert_project


def do_connect(env, target, opts, register=True, fix_path_drift=False):
    root = env.root
    config = load_config(env, target)
    flag_plugins = [p for p in opts.get("plugins", "").split(",") if p]
    plugins, profile_name, profile_source, source, include_meta = \
        resolve_selection(env, target, config, opts.get("profile", ""), flag_plugins)
    if profile_source == "items":
        profile_source = "plugins"

    buckets = all_buckets(env)
    known_plugins = set(buckets) | {"generate-skill"}
    for p in plugins:
        if p not in known_plugins:
            die(f"unknown plugin: {p} (available: {', '.join(sorted(known_plugins))})")
    if include_meta and "generate-skill" not in plugins:
        plugins = list(plugins) + ["generate-skill"]
    plugins = sorted(set(plugins))

    if config.get("exclude"):
        print("NOTE: .swissknife.json 'exclude' is skill-granular and is ignored "
              "in plugin mode (plugins are bucket-granular)")

    print(f"Target:   {target}")
    print(f"Profile:  {profile_name or '-'} (via {source})")
    print(f"Source:   {root}")
    print(f"Plugins:  {' '.join(plugins)}")

    list_only = opts.get("list", False)
    dry_run = opts.get("dry_run", False)
    if list_only:
        return None

    settings_file = opts.get("file") or "settings.local.json"
    if settings_file not in ("settings.json", "settings.local.json"):
        die("--file должен быть settings.json или settings.local.json")
    dest = target / ".claude" / settings_file
    settings = {}
    if dest.exists():
        try:
            settings = json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{dest}: invalid JSON: {e}")

    marketplaces = settings.setdefault("extraKnownMarketplaces", {})
    our_source = {"source": "directory", "path": str(root)}
    if MARKETPLACE in marketplaces:
        existing = marketplaces[MARKETPLACE].get("source", {})
        if existing != our_source:
            if fix_path_drift and existing.get("source") == "directory":
                print(f"NOTE: путь marketplace устарел ({existing.get('path')}) — "
                      f"обновляю на {root}")
                marketplaces[MARKETPLACE] = {"source": our_source}
            else:
                print(f"NOTE: marketplace '{MARKETPLACE}' already declared with a "
                      f"different source — keeping it: {json.dumps(existing)}")
    else:
        marketplaces[MARKETPLACE] = {"source": our_source}

    enabled = settings.setdefault("enabledPlugins", {})
    added, skipped_false = [], []
    for p in plugins:
        key = f"{p}@{MARKETPLACE}"
        if key not in enabled:
            enabled[key] = True
            added.append(p)
        elif enabled[key] is False:
            skipped_false.append(p)
    drift = [k for k, v in enabled.items()
             if k.endswith(f"@{MARKETPLACE}") and v
             and k.split("@")[0] not in plugins]

    if dry_run:
        print(f"--- dry-run: {dest} ---")
        print(json.dumps(settings, ensure_ascii=False, indent=2))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.copy2(dest, f"{dest}.bak")
            print(f"Бэкап:    {dest}.bak")
        dest.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"Записано: {dest}")

    if added:
        print(f"Включены: {' '.join(added)}")
    if skipped_false:
        print(f"Пропущены (явный false): {' '.join(skipped_false)}")
    if drift:
        print(f"NOTE: включены сверх профиля (не трогаю): {' '.join(drift)}")

    # vendored-copy migration
    skills_path = config.get("skills_path") or AGENT_DEFAULTS["claude"]
    manifest_file = target / skills_path / MANIFEST
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        dest_root = manifest_file.parent
        stale = []
        for entry in manifest.get("skills", []):
            name = entry.get("flat_name") or entry.get("path", "")
            d = dest_root / name
            if name and d.is_dir() and \
                    str(d.resolve()).startswith(str(dest_root.resolve()) + os.sep):
                stale.append(d)
        if opts.get("cleanup_vendored") and not dry_run:
            for d in stale:
                shutil.rmtree(d)
            manifest_file.unlink()
            print(f"Удалены вендоренные копии: {len(stale)} skill dir(s) + манифест")
        else:
            print(f"NOTE: найдены вендоренные копии ({len(stale)} dir(s) в "
                  f"{dest_root}) — удалить: --cleanup-vendored")

    hub = opts.get("hub", False)
    if hub and not dry_run:
        generate_hub(env, target)
    elif not dry_run:
        print(f"Подсказка: корневой хаб скиллов — swissknifeman update или "
              f"перезапуск с --hub")

    record = {
        "path": str(target),
        "channel": "marketplace",
        "profile": profile_name,
        "profile_source": profile_source,
        "plugins": plugins,
        "settings_file": settings_file,
        "hub": hub or hub_artifacts_exist(target),
    }
    if register and not dry_run:
        upsert_project(env, record)

    print("Далее: перезапустите сессию Claude Code в проекте "
          "(или /plugin marketplace update swissknifeman)")
    return record


def cmd_connect(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--profile": "str", "--plugins": "str",
        "--file": "str", "--cleanup-vendored": "bool", "--list": "bool",
        "--dry-run": "bool", "--hub": "bool",
    })
    if opts["help"]:
        print("swissknifeman connect [--profile P|--plugins a,b] "
              "[--file settings.json|settings.local.json] [--cleanup-vendored] "
              "[--list] [--dry-run] [--hub]")
        return
    target, _ = resolve_target(env, opts, allow_home_confirm=True)
    do_connect(env, target, opts)
