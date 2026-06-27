"""connect — канал plugin marketplace Claude Code."""
import json
import shutil

from core import atomic_write_text, find_repo_root, safe_load_json

from .common import (AGENT_DEFAULTS, MANIFEST, MARKETPLACE, apply_permissions,
                     die, is_within, parse_flags)
from .config import (CORE_BUCKETS, CORE_PLUGIN, CORE_SKILLS, all_buckets,
                     load_config, resolve_selection, resolve_target)
from .hub import generate_hub, hub_artifacts_exist
from .state import upsert_project


def _resident_tokens(env, plugins):
    """Грубая оценка резидентного ⊕ tier-0 (name+description) выбранного набора плагинов —
    для «умного подключения»: видно цену ДО записи. core → CORE_SKILLS; бакет → все его скиллы;
    generate-skill → его скилл. Источник токен-математики ОДИН — budget.skill_budget (не дублируем).
    Возврат (tokens, n_skills)."""
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
    """True, если сгенерированный marketplace.json (в корне репо) объявляет plugin_name.
    Защита: на старом marketplace или в синтетическом тест-реестре курируемого `core` может
    не быть — тогда CORE-политика тихо его не пушит (как раньше для отсутствующих бакетов)."""
    mp = (find_repo_root(env.root) or env.root) / ".claude-plugin" / "marketplace.json"
    data = safe_load_json(mp, default={}) or {}
    return any(p.get("name") == plugin_name for p in data.get("plugins", []))


def do_connect(env, target, opts, register=True, fix_path_drift=False):
    root = env.root
    config = load_config(env, target)
    flag_plugins = [p for p in opts.get("plugins", "").split(",") if p]
    plugins, profile_name, profile_source, source, include_meta = \
        resolve_selection(env, target, config, opts.get("profile", ""), flag_plugins)
    if profile_source == "items":
        profile_source = "plugins"

    buckets = all_buckets(env)
    known_plugins = set(buckets) | {"generate-skill", CORE_PLUGIN}
    # CORE-политика (умное подключение): вместо целых бакетов general(19)+oss-dev(10) ≈ 1956
    # резидентных токенов пушим лёгкий курируемый плагин `core` (== CORE_SKILLS, 7 ≈ 480 ток) —
    # экономия ~1.5K ток/проект на КАЖДЫЙ запрос. --no-core отключает. Плагин объявлен в
    # marketplace (registry.py); на старом marketplace / в тест-реестре его может не быть —
    # тогда тихо пропускаем (как раньше для отсутствующих бакетов).
    core_added = []
    if (not opts.get("no_core") and CORE_PLUGIN not in plugins
            and _marketplace_declares(env, CORE_PLUGIN)):
        core_added = [CORE_PLUGIN]
        plugins = list(plugins) + core_added

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
    resident, n_res = _resident_tokens(env, plugins)
    print(f"Резидент: ~{resident} ток ⊕ tier-0 ({n_res} скиллов, name+description в КАЖДОМ "
          f"запросе; тела — по триггеру). Меньше = дешевле: уже профиль или --no-core.")
    if source == "autodetect-fallback":
        print("⚠ ВНИМАНИЕ: тип проекта не распознан — поставлен МИНИМАЛЬНЫЙ набор (ядро),\n"
              "  а не «всё подряд». Для оптимального набора укажи профиль явно:\n"
              "  skiller connect --profile <node-frontend|laravel-project|php-package|…>\n"
              "  или точный список: skiller connect --plugins a,b,c")
    if core_added:
        print(f"CORE:     {CORE_PLUGIN} (лёгкое токен-экономное ядро, {len(CORE_SKILLS)} скиллов "
              f"вместо бакетов general+oss-dev; --no-core отключает)")

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
            elif existing.get("source") == "directory":
                # directory-источник с ДРУГИМ путём — вероятно репозиторий переехал: плагины
                # не подхватятся. Подсказку делаем действенной (а не молча оставляем старый путь).
                print(f"⚠ marketplace '{MARKETPLACE}' указывает на ДРУГОЙ каталог: "
                      f"{existing.get('path')}\n  реестр сейчас здесь: {mp_root}. Если "
                      f"репозиторий переехал — плагины не загрузятся. Исправить: "
                      f"skiller connect --fix-path (или skiller update).")
            else:
                # Иной тип источника (github/…) — осознанный выбор пользователя, не трогаем.
                print(f"NOTE: marketplace '{MARKETPLACE}' объявлен с другим источником "
                      f"({json.dumps(existing)}) — оставляю как есть.")
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

    # Миграция со старой CORE-политики (целые бакеты general+oss-dev) на лёгкий core-плагин:
    # если они остались включёнными ВНЕ активного профиля — теперь это лишний резидентный вес
    # (их 7 токен-скиллов уже даёт `core`). Подсказываем снять; merge-only — сами не трогаем.
    if core_added:
        legacy = [b for b in CORE_BUCKETS
                  if enabled.get(f"{b}@{MARKETPLACE}") and b not in plugins]
        if legacy:
            print(f"NOTE: старые CORE-бакеты включены сверх профиля: {' '.join(legacy)} — теперь "
                  f"их заменяет лёгкий '{CORE_PLUGIN}'. Для экономии токенов отключите их в "
                  f"{settings_file}: \"{legacy[0]}@{MARKETPLACE}\": false (и т.д.)")

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
