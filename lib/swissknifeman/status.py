"""status — read-only отчёт по проекту."""
import json
import os
from pathlib import Path

from .common import MANIFEST, MARKETPLACE, die, parse_flags
from .config import find_project_root, load_config, resolve_selection
from .state import db_records, print_registry_state
from .update import detect_marketplace_file, detect_vendor_path


def cmd_status(env, argv):
    opts = parse_flags(argv, {"--target": "str"})
    if opts["help"]:
        print("swissknifeman status")
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

    mk_file = detect_marketplace_file(target)
    if mk_file:
        s = json.loads((target / ".claude" / mk_file).read_text(encoding="utf-8"))
        src = s["extraKnownMarketplaces"][MARKETPLACE].get("source", {})
        moved = src != {"source": "directory", "path": str(env.root)}
        print(f"\nКанал marketplace ({mk_file}):")
        print(f"  Источник: {src.get('path', json.dumps(src))}"
              + ("  [ПЕРЕЕХАЛ — починить: swissknifeman update]" if moved else ""))
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
                  f"(добавить: swissknifeman update)")
        if extra:
            print(f"  Сверх профиля: {' '.join(extra)}")
    vendor_path = detect_vendor_path(target, config)
    if vendor_path:
        mf = target / vendor_path / MANIFEST
        manifest = json.loads(mf.read_text(encoding="utf-8"))
        skills = manifest.get("skills", [])
        gone = [e.get("source_path", "") for e in skills
                if e.get("source_path") and not (env.root / e["source_path"]).exists()]
        print(f"\nКанал vendor ({vendor_path}, layout {manifest.get('layout')}):")
        print(f"  Скиллов: {len(skills)}, установлено {manifest.get('installed_at')}"
              f", агент {manifest.get('agent')}, профиль {manifest.get('profile') or '-'}")
        if gone:
            print(f"  Удалены/переименованы в реестре ({len(gone)}): "
                  + " ".join(gone[:5]) + (" …" if len(gone) > 5 else "")
                  + "  (почистить: swissknifeman update)")
    if not mk_file and not vendor_path:
        print("\nКаналы: не подключён (swissknifeman connect | vendor)")
    print()
    print_registry_state(env)
