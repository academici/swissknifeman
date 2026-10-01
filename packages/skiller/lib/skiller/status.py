"""status — read-only отчёт по проекту."""
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

# maind sync writes these at fixed paths; they share registry names with
# repository-bootstrap but are NOT skiller-vendored copies (see skilldoc.py).
MAIND_MANAGED_SKILL_NAMES = frozenset({"ecosystem-mcp", "ecosystem-setup"})


def _bucket_of(source_path):
    """Бакет из source_path вендоренного скилла ('skills/<bucket>/<rel>' → bucket)."""
    parts = Path(source_path).parts
    return parts[1] if len(parts) >= 2 and parts[0] == "skills" else None


def channel_overlap(enabled, vendored_buckets):
    """Бакеты, активные ОДНОВРЕМЕННО как плагин (connect) и вендоренные (vendor) —
    скиллы такого бакета раздаются дважды. Возвращает отсортированный список."""
    return sorted(set(enabled) & set(vendored_buckets))


def detect_raw_vendor_path(target, config):
    """Вендорный канал БЕЗ манифеста: скиллы приехали симлинками/копиями
    из стороннего источника (`.ai/skills` и т.п.), не через `skiller sync` — у
    `detect_vendor_path` (нужен `.swissknifeman-manifest.json`) такой канал невидим,
    и `channel_overlap` на нём молчит (репо-факт `flexcrm`,
    `findings/P3-listing-hygiene-and-vendoring-facts.md` §2.3). Возвращает первый
    непустой из тех же кандидатов, что и `detect_vendor_path`, БЕЗ требования манифеста."""
    config = ProjectConfig.coerce(config)  # исторические вызовы передают dict
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
    """Записи локального каталога скиллов (symlinks+каталоги), включая мёртвые.
    -> [{"dir": имя, "dead": bool, "name": frontmatter name | None}]. `dead` —
    битый симлинк ИЛИ каталог без `SKILL.md` (P3.5 дельта в, репо-факт `flexcrm`:
    41 битый симлинк из 58 записей)."""
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
    """frontmatter `name` -> [бакеты], по ВСЕМУ реестру (не только включённым
    бакетам): дубль — это вторая физическая копия скилла реестра, живущая вне
    реестра и не обновляемая `skiller update`, независимо от того, включён ли
    сегодня бакет-донор (P3.5 дельта б)."""
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
    """Живые локальные записи, чьё frontmatter `name` уже есть где-то в реестре —
    дубль ИМЕНИ (не каталога: у части скиллов каталог переименован при сохранённом
    `name`, см. `findings/P3-listing-hygiene-and-vendoring-facts.md` §6).

    maind-managed ecosystem skills share registry names but are updated by
    ``maind sync``, not ``skiller update`` — exclude them from duplicate warnings."""
    return sorted(
        (e["dir"], e["name"], tuple(registry_names[e["name"]]))
        for e in local_entries
        if (not e["dead"] and e["name"] in registry_names
            and e["name"] not in MAIND_MANAGED_SKILL_NAMES)
    )


def raw_vendor_overlap_dirs(local_entries, registry_names, enabled_buckets):
    """Локальные записи raw vendor, чьи имена перекрывают активные marketplace-бакеты.

    Используется ``connect --cleanup-vendored`` для миграции legacy symlinks из
    ``.ai/skills`` (репо-факт insiders/flexcrm — канал без манифеста)."""
    enabled = set(enabled_buckets)
    return sorted(
        e["dir"] for e in local_entries
        if (not e["dead"] and e["name"] in registry_names
            and e["name"] not in MAIND_MANAGED_SKILL_NAMES
            and enabled.intersection(registry_names[e["name"]]))
    )


def remove_raw_vendor_entries(skills_dir, dirs, *, dry_run=False):
    """Удалить перечисленные записи из каталога raw vendor (symlink или каталог)."""
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
    """Имена мёртвых локальных записей (диагностично: что именно мертво)."""
    return sorted(e["dir"] for e in local_entries if e["dead"])


def prune_orphan_managed_lock(target, *, dry_run=False):
    """Снять managed-записи skills-lock, чьи installed_path больше не существуют.

    Типичный след ``connect --cleanup-vendored``: физ. копии сняты, lock остался и
    вводит в заблуждение ``maind projects status`` / derive-граф."""
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
        print(f"NOTE: skills-lock: {len(orphans)} managed-записей без файлов — "
              "удалить: --cleanup-vendored (повторно)")
        return len(orphans)
    if kept:
        data["skills"] = kept
        atomic_write_json(lock_path, data)
    else:
        lock_path.unlink()
    print(f"Очищен skills-lock: снято {len(orphans)} orphan managed-записей")
    return len(orphans)


def cmd_status(env, argv):
    opts = parse_flags(argv, {"--target": "str", "--json": "bool"})
    if opts["help"]:
        print("skiller status [--target DIR] [--json]")
        return
    js = opts.get("json")

    def out(s=""):                              # текст — только в человекочитаемом режиме
        if not js:
            print(s)

    if opts.get("target"):
        target = Path(os.path.expanduser(opts["target"])).resolve()
        via = "--target"
    else:
        target, via = find_project_root(env)
        if target is None:
            die("корень проекта не найден выше CWD")
    config = load_config(env, target)
    out(f"Проект:   {target} (по маркеру {via})")
    registered = {r["channel"] for r in db_records(env, target)}
    out(f"Реестр:   {env.root}")
    out(f"В projects.json: "
        f"{', '.join(sorted(registered)) if registered else 'не зарегистрирован'}")
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
        # marketplace.json лежит в КОРНЕ монорепо (туда же connect/update пишут source),
        # а не в каталоге пакета env.root — сравниваем с тем же корнем, иначе в монорепо
        # вечный ложный [ПЕРЕЕХАЛ], который skiller update не способен погасить.
        mp_root = find_repo_root(env.root) or env.root
        moved = src != {"source": "directory", "path": str(mp_root)}
        out(f"\nКанал marketplace ({mk_file}):")
        out(f"  Источник: {src.get('path', json.dumps(src))}"
            + ("  [ПЕРЕЕХАЛ — починить: skiller update]" if moved else ""))
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
        out(f"  Включены: {' '.join(sorted(enabled)) or '-'}")
        if disabled:
            out(f"  Выключены явно: {' '.join(sorted(disabled))}")
        out(f"  Профиль:  {profile_name or '-'} (via {source})")
        if missing:
            out(f"  Не хватает по профилю: {' '.join(missing)} "
                f"(добавить: skiller update)")
        if extra:
            out(f"  Сверх профиля: {' '.join(extra)}")
        # включённый бакет слит в другой (alias) — одна строка-подсказка, без
        # нагнетания; status read-only, ничего не переключает сама.
        alias_hints = alias_migration_hints(load_bucket_aliases(env), enabled)
        for h in alias_hints:
            out(f"  Подсказка: {h}")
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
        out(f"\nКанал vendor ({vendor_path}, layout {manifest.get('layout')}):")
        out(f"  Скиллов: {len(skills)}, установлено {manifest.get('installed_at')}"
            f", агент {manifest.get('agent')}, профиль {manifest.get('profile') or '-'}")
        if gone:
            out(f"  Удалены/переименованы в реестре ({len(gone)}): "
                + " ".join(gone[:5]) + (" …" if len(gone) > 5 else "")
                + "  (почистить: skiller update)")
        report["vendor"] = {
            "path": vendor_path, "layout": manifest.get("layout"), "count": len(skills),
            "installed_at": manifest.get("installed_at"), "agent": manifest.get("agent"),
            "profile": manifest.get("profile"), "gone": gone}
        local_entries = local_channel_entries(target / vendor_path)
    else:
        # P3.5 дельта а: канал без манифеста (симлинки/копии со стороны, не
        # через `skiller sync`) — раньше был невидим для этой команды и для
        # channel_overlap (репо-факт flexcrm: 58 записей, манифеста нет).
        raw_vendor_path = detect_raw_vendor_path(target, config)
        if raw_vendor_path:
            local_entries = local_channel_entries(target / raw_vendor_path)
            live = [e for e in local_entries if not e["dead"]]
            out(f"\nКанал vendor ({raw_vendor_path}, БЕЗ манифеста — не через "
                f"skiller sync/vendor):")
            out(f"  Записей: {len(local_entries)} ({len(live)} живых, "
                f"{len(local_entries) - len(live)} мёртвых)")
    if not mk_file and not vendor_path and not raw_vendor_path:
        out("\nКаналы: не подключён (skiller connect | vendor)")

    dup = dead = []
    if local_entries:
        registry_names = registry_skill_names(env)
        dup = name_duplicates(local_entries, registry_names)
        dead = dead_local_entries(local_entries)
        if not vendor_path:
            # манифеста нет — единственный источник "вендоренных бакетов" для
            # channel_overlap ниже: бакеты-доноры имён, которые local делит с реестром.
            vendored_buckets = {b for _dir, _name, buckets in dup for b in buckets}
        if dup:
            out(f"\n⚠ ДУБЛИ ИМЁН с реестром ({len(dup)}): " + ", ".join(
                f"{d}→{'/'.join(b)}" for d, _n, b in dup[:8])
                + (" …" if len(dup) > 8 else ""))
            out("  Локальная копия не обновляется `skiller update` — либо снять "
                "локальную запись, либо подключить бакет-донор штатным каналом.")
        if dead:
            out(f"\n⚠ МЁРТВЫЕ ЗАПИСИ ({len(dead)}): битые симлинки/каталоги без "
                "SKILL.md — " + ", ".join(dead[:8]) + (" …" if len(dead) > 8 else ""))
            out("  Почистить: find <канал> -maxdepth 1 -xtype l -delete "
                "(проверь список выше перед массовым удалением).")
    report["name_duplicates"] = [{"dir": d, "name": n, "buckets": list(b)}
                                  for d, n, b in dup]
    report["dead_entries"] = dead

    # Токеновый бюджет набора (контроль раздувания): ⊕ always — постоянный налог
    # описаний, резидентный в каждом запросе. Подробности/карта — skiller budget.
    try:
        skills, meta = resolve_active_set(env, target, config)
        b = budget_for_set(skills, meta["pulled"])
        top = sorted(b["items"], key=lambda i: i["tier0"], reverse=True)[:3]
        out(f"\nТокеновый бюджет набора (≈, профиль {meta['profile'] or '-'}):")
        out(f"  ⊕ always {b['tier0']} ток · ↻ bodies {b['tier1']} ток · "
            f"{b['count']} скиллов  (детали: skiller budget)")
        if top:
            out("  Топ ⊕: " + ", ".join(
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
    except Exception as e:  # бюджет не должен ронять status
        out(f"\nТокеновый бюджет: недоступен ({e})")

    # Гигиена каналов: один бакет не должен раздаваться И плагином, И вендором —
    # иначе скиллы дублируются. Проверка живёт ТОЛЬКО здесь (skiller — владелец
    # скиллов); зонтик дёргает её через `swissknifeman skills status`, не дублируя.
    overlap = channel_overlap(enabled, vendored_buckets)
    report["channel_overlap"] = overlap
    if overlap:
        out(f"\n⚠ ДУБЛЬ КАНАЛОВ: бакеты [{' '.join(overlap)}] активны ОДНОВРЕМЕННО как "
            f"плагины (connect) и вендорены (vendor) — скиллы раздаются дважды.")
        out("  Оставь один канал: убери бакет из enabledPlugins (connect) ИЛИ из "
            ".swissknifeman/config.json (vendor) + skiller sync.")
    if js:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print()
    print_registry_state(env)
