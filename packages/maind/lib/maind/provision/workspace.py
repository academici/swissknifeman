"""Единое пространство доверия Claude Code, управляемое из хаба maind (hub-scoped).

Проблема: при правке смежных проектов Claude Code задаёт запрос «доверять каталогу?»
(граница рабочего пространства). Это ОТДЕЛЬНАЯ от allow/deny система — bypassPermissions
её НЕ глушит. Фикс — внести пути всех проектов экосистемы в
permissions.additionalDirectories настроек.

Модуль генерирует/сопровождает .claude/settings.local.json В КОРНЕ maind: доверие
получает сессия Claude, запущенная из хаба. Реестр проектов (.maind.json) — единственный
источник правды. Запись идемпотентна и АДДИТИВНА: чужие записи и заданный пользователем
defaultMode не трогаем. Зеркало mcpconfig.py (load → merge → write) для настроек Claude."""
import copy
import json
import os
from pathlib import Path

from ..common import atomic_write_json, backup_file, die, parse_args
from ..config import load_config

DEFAULT_MODE = "acceptEdits"


def hub_settings_path(env):
    """Где живут hub-настройки доверия (gitignored, абсолютные персональные пути)."""
    return env.root / ".claude" / "settings.local.json"


def norm_path(p):
    """Нормализация пути для сравнения/дедупа: expanduser + realpath (резолвит симлинки и
    `.`/`..`-сегменты). N4: раньше был только normpath — повторный `maind onboard` через
    симлинк/иной эквивалентный путь на тот же каталог штамповал дубль-запись проекта
    (_ensure_project матчит по нормализованному local_path). realpath безопасен и для
    несуществующих путей (резолвит существующий префикс, остаток оставляет как есть)."""
    return os.path.realpath(os.path.expanduser(str(p)))


def load_settings(path):
    """(data, existed). Нет файла → ({}, False). Битый JSON → die (НЕ трогаем чужой файл)."""
    path = Path(path)
    if not path.exists():
        return {}, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path}: битый JSON настроек Claude — не трогаю, исправьте вручную: {e}")
    if not isinstance(data, dict):
        die(f"{path}: ожидался объект настроек Claude")
    return data, True


def eligible_paths(config):
    """Отсортированный уникальный список абсолютных путей включённых проектов, чей
    каталог существует на диске. Без local_path / disabled / отсутствующий путь — пропуск."""
    seen = set()
    for p in config.get("projects") or []:
        if p.get("enabled") is False:
            continue
        lp = p.get("local_path")
        if not lp:
            continue
        norm = norm_path(lp)
        if Path(norm).is_dir():
            seen.add(norm)
    return sorted(seen)


def build_fragment(paths, *, allow=True, mode=True):
    """Фрагмент настроек Claude для доверенных каталогов.

    additionalDirectories чинит границу рабочего пространства; allow (Read/Edit-глобы)
    и defaultMode дополнительно убирают трение даже без bypass. Абсолютный путь в
    permission-правиле — с двойным слешем: Read(//abs/path/**)."""
    perms = {"additionalDirectories": list(paths)}
    if allow:
        rules = []
        for p in paths:
            rules.append(f"Read(/{p}/**)")
            rules.append(f"Edit(/{p}/**)")
        perms["allow"] = rules
    if mode:
        perms["defaultMode"] = DEFAULT_MODE
    return {"permissions": perms}


def merge_settings(existing, fragment):
    """Сливает fragment в existing идемпотентно/аддитивно. Возвращает (merged, changed).

    Списки (additionalDirectories, allow) — union с дедупом, порядок существующих и
    чужих записей сохраняется. defaultMode ставим, ТОЛЬКО если он ещё не задан (не
    перетираем выбор пользователя). Любые посторонние ключи настроек сохраняются."""
    merged = copy.deepcopy(existing) if existing else {}
    changed = False
    perms = merged.get("permissions")
    if not isinstance(perms, dict):
        perms = {}
        merged["permissions"] = perms
    fperms = fragment.get("permissions") or {}

    for key in ("additionalDirectories", "allow"):
        incoming = fperms.get(key)
        if not incoming:
            continue
        cur = perms.get(key)
        cur = list(cur) if isinstance(cur, list) else []
        have = set(cur)
        for item in incoming:
            if item not in have:
                cur.append(item)
                have.add(item)
                changed = True
        perms[key] = cur

    if "defaultMode" in fperms and "defaultMode" not in perms:
        perms["defaultMode"] = fperms["defaultMode"]
        changed = True

    return merged, changed


def sync(env, config, *, allow=True, mode=True, dry=False, backup=True):
    """Записать/обновить hub-настройки доверия из реестра проектов. Возвращает метаданные.
    dry=True — ничего не пишет (вернёт предполагаемый merged в result['settings'])."""
    path = hub_settings_path(env)
    existing, _existed = load_settings(path)
    paths = eligible_paths(config)
    fragment = build_fragment(paths, allow=allow, mode=mode)

    before = existing.get("permissions") or {}
    before_dirs = set(before.get("additionalDirectories") or [])
    before_allow = set(before.get("allow") or [])
    had_mode = "defaultMode" in before

    merged, changed = merge_settings(existing, fragment)
    after = merged.get("permissions") or {}
    result = {
        "path": str(path),
        "total_paths": len(paths),
        "dirs_added": sorted(set(after.get("additionalDirectories") or []) - before_dirs),
        "allow_added": len(set(after.get("allow") or []) - before_allow),
        "mode_set": (not had_mode) and ("defaultMode" in after),
        "changed": changed,
        "dry": dry,
        "settings": merged,
    }
    if not dry and changed:
        if backup:
            backup_file(path)
        atomic_write_json(path, merged)
    return result


def trusted_dirs(env):
    """Множество доверенных каталогов из hub-настроек (нормализованных). Нет/битый → пустое."""
    path = hub_settings_path(env)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    dirs = (data.get("permissions") or {}).get("additionalDirectories") or []
    return {norm_path(d) for d in dirs}


def audit(env, config):
    """Read-only диф реестра и hub-настроек: covered / missing / drift."""
    trusted = trusted_dirs(env)
    registry = {}  # norm_path → project id
    for p in config.get("projects") or []:
        lp = p.get("local_path")
        if lp:
            registry[norm_path(lp)] = p.get("id")
    reg = set(registry)
    return {
        "settings": str(hub_settings_path(env)),
        "trusted_count": len(trusted),
        "registry_count": len(reg),
        "covered": [{"id": registry[p], "path": p} for p in sorted(reg & trusted)],
        "missing": [{"id": registry[p], "path": p} for p in sorted(reg - trusted)],
        "drift": sorted(trusted - reg),  # доверено, но не из реестра
    }


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_workspace(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind workspace <sync|status> "
              "[--dry-run] [--no-allow] [--no-mode] [--json]")
        return
    sub, rest = argv[0], argv[1:]
    if sub == "sync":
        _cmd_sync(env, rest)
    elif sub == "status":
        _cmd_status(env, rest)
    else:
        die(f"неизвестная подкоманда workspace: {sub} (sync|status)")


def _cmd_sync(env, argv):
    opts, _ = parse_args(argv, {"--dry-run": "bool", "--no-allow": "bool",
                                "--no-mode": "bool", "--json": "bool"})
    config, _src = load_config(env)
    result = sync(env, config, allow=not opts["no_allow"],
                  mode=not opts["no_mode"], dry=opts["dry_run"])
    if opts["json"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    tag = "[dry-run] " if result["dry"] else ""
    if result["changed"]:
        extra = f", allow +{result['allow_added']}" if result["allow_added"] else ""
        extra += f", defaultMode={DEFAULT_MODE}" if result["mode_set"] else ""
        print(f"{tag}Доверие → {result['path']}")
        print(f"  каталогов: {result['total_paths']} "
              f"(добавлено {len(result['dirs_added'])}){extra}")
    else:
        print(f"{tag}Доверие уже актуально ({result['total_paths']} каталогов) "
              f"→ {result['path']}")
    if result["dry"] and result["changed"]:
        print(json.dumps(result["settings"], ensure_ascii=False, indent=2))


def _cmd_status(env, argv):
    opts, _ = parse_args(argv, {"--json": "bool"})
    config, _src = load_config(env)
    a = audit(env, config)
    if opts["json"]:
        print(json.dumps(a, ensure_ascii=False, indent=2))
        return
    print(f"Доверие Claude (hub): {a['settings']}")
    print(f"  доверено {len(a['covered'])}/{a['registry_count']} проектов реестра")
    for m in a["missing"]:
        print(f"  ✗ не доверен: {m['id']} ({m['path']})")
    for d in a["drift"]:
        print(f"  ? лишний каталог (не из реестра): {d}")
