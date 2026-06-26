"""connect — канал plugin marketplace Claude Code."""
import json
import shutil

from core import atomic_write_text, find_repo_root

from .common import (AGENT_DEFAULTS, MANIFEST, MARKETPLACE, apply_permissions,
                     die, is_within, parse_flags)
from .config import (CORE_BUCKETS, all_buckets, load_config, resolve_selection,
                     resolve_target)
from .hub import generate_hub, hub_artifacts_exist
from .state import upsert_project


def do_connect(env, target, opts, register=True, fix_path_drift=False):
    root = env.root
    config = load_config(env, target)
    flag_plugins = [p for p in opts.get("plugins", "").split(",") if p]
    plugins, profile_name, profile_source, source, include_meta = \
        resolve_selection(env, target, config, opts.get("profile", ""), flag_plugins)
    if profile_source == "items":
        profile_source = "plugins"

    buckets = all_buckets(env)
    # CORE: marketplace bucket-granular → раздаём токен-бакеты general+oss-dev в
    # каждый проект (skill-level CORE недоступен в plugin-режиме). --no-core отключает.
    # Только существующие бакеты (реестр может их не содержать — напр. в тестах).
    core_added = []
    if not opts.get("no_core"):
        core_added = [b for b in CORE_BUCKETS if b not in plugins and b in buckets]
        plugins = list(plugins) + core_added

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
    if source == "autodetect-fallback":
        print("⚠ ВНИМАНИЕ: тип проекта не распознан — поставлен МИНИМАЛЬНЫЙ набор (ядро),\n"
              "  а не «всё подряд». Для оптимального набора укажи профиль явно:\n"
              "  skiller connect --profile <node-frontend|laravel-project|php-package|…>\n"
              "  или точный список: skiller connect --plugins a,b,c")
    if core_added:
        print(f"CORE:     {' '.join(core_added)} (токен-бакеты по умолчанию; --no-core отключает)")

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
    # marketplace.json лежит в КОРНЕ монорепо (registry пишет туда же, source-пути
    # относительны корня), а не в каталоге пакета env.root — иначе Claude Code ищет
    # .claude-plugin/marketplace.json под packages/skiller и не находит плагины.
    mp_root = find_repo_root(root) or root
    our_source = {"source": "directory", "path": str(mp_root)}
    if MARKETPLACE in marketplaces:
        existing = marketplaces[MARKETPLACE].get("source", {})
        if existing != our_source:
            if fix_path_drift and existing.get("source") == "directory":
                print(f"NOTE: путь marketplace устарел ({existing.get('path')}) — "
                      f"обновляю на {mp_root}")
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
        if dest.exists():
            shutil.copy2(dest, f"{dest}.bak")
            print(f"Бэкап:    {dest}.bak")
        atomic_write_text(dest,
                          json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        print(f"Записано: {dest}")

    if added:
        print(f"Включены: {' '.join(added)}")
    if skipped_false:
        print(f"Пропущены (явный false): {' '.join(skipped_false)}")
    if drift:
        print(f"NOTE: включены сверх профиля (не трогаю): {' '.join(drift)}")

    # permissions-пресеты (deny мусора + allow стека) в тот же settings-файл
    if not opts.get("no_permissions"):
        apply_permissions(env, target, settings_file=settings_file, dry_run=dry_run)

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
            if name and d.is_dir() and is_within(d, dest_root):
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
        print("Подсказка: корневой хаб скиллов — skiller update или "
              "перезапуск с --hub")

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
        "--dry-run": "bool", "--hub": "bool", "--no-core": "bool",
        "--no-permissions": "bool", "--fix-path": "bool",
    })
    if opts["help"]:
        print("skiller connect [--profile P|--plugins a,b] "
              "[--file settings.json|settings.local.json] [--cleanup-vendored] "
              "[--list] [--dry-run] [--hub] [--no-core] [--no-permissions] "
              "[--fix-path]")
        return
    target, _ = resolve_target(env, opts, allow_home_confirm=True)
    do_connect(env, target, opts, fix_path_drift=opts.get("fix_path", False))
