"""status — read-only отчёт по проекту."""
import json
import os
from pathlib import Path

from .budget import budget_for_set, resolve_active_set
from .common import MANIFEST, MARKETPLACE, die, parse_flags
from .config import find_project_root, load_config, resolve_selection
from .state import db_records, print_registry_state
from .update import detect_marketplace_file, detect_vendor_path


def _bucket_of(source_path):
    """Бакет из source_path вендоренного скилла ('skills/<bucket>/<rel>' → bucket)."""
    parts = Path(source_path).parts
    return parts[1] if len(parts) >= 2 and parts[0] == "skills" else None


def channel_overlap(enabled, vendored_buckets):
    """Бакеты, активные ОДНОВРЕМЕННО как плагин (connect) и вендоренные (vendor) —
    скиллы такого бакета раздаются дважды. Возвращает отсортированный список."""
    return sorted(set(enabled) & set(vendored_buckets))


def cmd_status(env, argv):
    opts = parse_flags(argv, {"--target": "str"})
    if opts["help"]:
        print("skiller status")
        return
    if opts.get("target"):
        target = Path(os.path.expanduser(opts["target"])).resolve()
        via = "--target"
    else:
        target, via = find_project_root(env)
        if target is None:
            die("корень проекта не найден выше CWD")
    config = load_config(env, target)
    print(f"Проект:   {target} (по маркеру {via})")
    registered = {r["channel"] for r in db_records(env, target)}
    print(f"Реестр:   {env.root}")
    print(f"В projects.json: "
          f"{', '.join(sorted(registered)) if registered else 'не зарегистрирован'}")

    enabled = []
    vendored_buckets = set()
    mk_file = detect_marketplace_file(target)
    if mk_file:
        s = json.loads((target / ".claude" / mk_file).read_text(encoding="utf-8"))
        src = s["extraKnownMarketplaces"][MARKETPLACE].get("source", {})
        moved = src != {"source": "directory", "path": str(env.root)}
        print(f"\nКанал marketplace ({mk_file}):")
        print(f"  Источник: {src.get('path', json.dumps(src))}"
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
        print(f"  Включены: {' '.join(sorted(enabled)) or '-'}")
        if disabled:
            print(f"  Выключены явно: {' '.join(sorted(disabled))}")
        print(f"  Профиль:  {profile_name or '-'} (via {source})")
        if missing:
            print(f"  Не хватает по профилю: {' '.join(missing)} "
                  f"(добавить: skiller update)")
        if extra:
            print(f"  Сверх профиля: {' '.join(extra)}")
    vendor_path = detect_vendor_path(target, config)
    if vendor_path:
        mf = target / vendor_path / MANIFEST
        manifest = json.loads(mf.read_text(encoding="utf-8"))
        skills = manifest.get("skills", [])
        gone = [e.get("source_path", "") for e in skills
                if e.get("source_path") and not (env.root / e["source_path"]).exists()]
        vendored_buckets = {b for e in skills
                            if (b := _bucket_of(e.get("source_path", "")))}
        print(f"\nКанал vendor ({vendor_path}, layout {manifest.get('layout')}):")
        print(f"  Скиллов: {len(skills)}, установлено {manifest.get('installed_at')}"
              f", агент {manifest.get('agent')}, профиль {manifest.get('profile') or '-'}")
        if gone:
            print(f"  Удалены/переименованы в реестре ({len(gone)}): "
                  + " ".join(gone[:5]) + (" …" if len(gone) > 5 else "")
                  + "  (почистить: skiller update)")
    if not mk_file and not vendor_path:
        print("\nКаналы: не подключён (skiller connect | vendor)")

    # Токеновый бюджет набора (контроль раздувания): ⊕ always — постоянный налог
    # описаний, резидентный в каждом запросе. Подробности/карта — skiller budget.
    try:
        skills, meta = resolve_active_set(env, target, config)
        b = budget_for_set(skills, meta["pulled"])
        top = sorted(b["items"], key=lambda i: i["tier0"], reverse=True)[:3]
        print(f"\nТокеновый бюджет набора (≈, профиль {meta['profile'] or '-'}):")
        print(f"  ⊕ always {b['tier0']} ток · ↻ bodies {b['tier1']} ток · "
              f"{b['count']} скиллов  (детали: skiller budget)")
        if top:
            print("  Топ ⊕: " + ", ".join(
                f"{i['name']} ({i['tier0']})" for i in top))
    except SystemExit:
        raise
    except Exception as e:  # бюджет не должен ронять status
        print(f"\nТокеновый бюджет: недоступен ({e})")

    # Гигиена каналов: один бакет не должен раздаваться И плагином, И вендором —
    # иначе скиллы дублируются. Проверка живёт ТОЛЬКО здесь (skiller — владелец
    # скиллов); зонтик дёргает её через `swissknifeman skills status`, не дублируя.
    overlap = channel_overlap(enabled, vendored_buckets)
    if overlap:
        print(f"\n⚠ ДУБЛЬ КАНАЛОВ: бакеты [{' '.join(overlap)}] активны ОДНОВРЕМЕННО как "
              f"плагины (connect) и вендорены (vendor) — скиллы раздаются дважды.")
        print("  Оставь один канал: убери бакет из enabledPlugins (connect) ИЛИ из "
              ".swissknifeman/config.json (vendor) + skiller sync.")
    print()
    print_registry_state(env)
