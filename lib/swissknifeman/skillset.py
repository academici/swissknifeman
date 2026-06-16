"""skillset — vendor-режим на едином конфиге .swissknifeman/config.json.

Единый источник истины для физического переноса скиллов в проект: конфиг в
`.swissknifeman/config.json` задаёт правила (конкретные скиллы + бакеты целиком −
исключения), `sync` разворачивает их в плоский набор, копирует файлы в репо и
пишет производный `skills-lock.json` с пометкой происхождения.

Поток (config → lock → файлы):

    .swissknifeman/config.json   (источник истины, правит человек)
            ↓ resolve_skillset    разворот правил в плоский набор скиллов
       набор скиллов из библиотеки swissknifeman (по skills.json)
            ↓ sync_skillset       install + update(по sha256) + prune(по managed)
    .claude/skills/<name>/        физические копии (видит Claude)
    skills-lock.json             производная карта: managed-записи + чужие нетронуты

Безопасное удаление: prune трогает ТОЛЬКО записи managed=true, которых больше нет
в конфиге. Чужие скиллы (managed отсутствует/false — ручной вендоринг, наследие
Boost, скиллы из другого хаба) синк не удаляет. См. [[lock]] — read-only композитор
остаётся для проектов без vendor-режима.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path

from .common import die, parse_flags, warn
from .config import all_buckets, resolve_target

# Куда складываем скиллы по умолчанию (Claude находит автоматически).
DEFAULT_SKILLS_PATH = ".claude/skills"
CONFIG_DIR = ".swissknifeman"
CONFIG_FILE = "config.json"
LOCK_FILE = "skills-lock.json"
LOCK_VERSION = 1
SOURCE = "swissknifeman"

# Ключи конфига vendor-режима (.swissknifeman/config.json). Намеренно шире
# .swissknife.json — это отдельный, расширяемый конфиг режима физ. переноса.
SKILLSET_KEYS = {
    "version": int,
    "mode": str,          # пока только "vendor"
    "agent": str,         # информативно; путь задаёт skills_path
    "skills_path": str,   # куда копировать (по умолчанию .claude/skills)
    "include": list,      # конкретные скиллы: "bucket/rel" или просто "name"
    "buckets": list,      # бакеты целиком
    "exclude": list,      # вычитание из (buckets ∪ include)
}


# --- registry index (источник истины — skills.json) ---------------------------
def _registry_index(env):
    """skills.json → {key: entry}, где key — и полный путь 'bucket/rel', и имя.

    entry = {name, bucket, rel, path(SKILL.md, отн. корня реестра), sha256,
             skill_dir(абс.)}. Реестр — единственный источник, по которому
    резолвятся и проверяются на дрейф наши скиллы."""
    f = env.root / "skills.json"
    if not f.is_file():
        die("skills.json не найден — сначала swissknifeman registry")
    data = json.loads(f.read_text(encoding="utf-8"))
    skills = data["skills"] if isinstance(data, dict) else data
    by_key = {}
    by_name = {}
    for s in skills:
        name = s.get("name") or s.get("id")
        bucket = s.get("bucket", "")
        path = s.get("path", "")  # "skills/<bucket>/<rel>/SKILL.md"
        if not (name and path):
            continue
        skill_dir = (env.root / path).parent
        # rel внутри бакета: skills/<bucket>/<rel>/SKILL.md → <rel>
        rel = ""
        parts = Path(path).parts
        if len(parts) >= 4 and parts[0] == "skills":
            rel = "/".join(parts[2:-1])
        entry = {
            "name": name, "bucket": bucket, "rel": rel, "path": path,
            "sha256": s.get("sha256", ""), "skill_dir": skill_dir,
        }
        full = f"{bucket}/{rel}".rstrip("/") if rel else bucket
        by_key[full] = entry
        by_name.setdefault(name, entry)
    return by_key, by_name


def _match(token, by_key, by_name):
    """Разрешить токен правила в entry: сначала по полному пути, потом по имени."""
    if token in by_key:
        return by_key[token]
    if token in by_name:
        return by_name[token]
    return None


# --- config -------------------------------------------------------------------
def skillset_config_path(target):
    return Path(target) / CONFIG_DIR / CONFIG_FILE


def load_skillset_config(target):
    """Прочитать .swissknifeman/config.json (или None, если его нет)."""
    cfg_file = skillset_config_path(target)
    if not cfg_file.is_file():
        return None
    try:
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{cfg_file}: невалидный JSON: {e}")
    import difflib
    for key, value in cfg.items():
        if key.startswith("_"):
            continue
        if key not in SKILLSET_KEYS:
            hint = difflib.get_close_matches(key, list(SKILLSET_KEYS), n=1)
            suffix = f" — может быть '{hint[0]}'?" if hint else ""
            die(f"{cfg_file}: неизвестный ключ '{key}'{suffix}")
        if not isinstance(value, SKILLSET_KEYS[key]):
            want = SKILLSET_KEYS[key].__name__
            die(f"{cfg_file}: '{key}' должен быть {want}")
    if cfg.get("mode", "vendor") != "vendor":
        die(f"{cfg_file}: поддерживается только mode=vendor")
    return cfg


def resolve_skillset(env, cfg):
    """Развернуть правила конфига в набор entry: (buckets ∪ include) − exclude.

    Возвращает (entries, skipped): entries отсортированы по 'bucket/name';
    skipped — токены, не найденные в реестре (с warning)."""
    by_key, by_name = _registry_index(env)
    known = set(all_buckets(env))
    selected = {}  # name -> entry (имя уникально в раскладке .claude/skills)
    skipped = []

    # бакеты целиком
    for bucket in cfg.get("buckets", []):
        if bucket not in known:
            die(f"неизвестный бакет: {bucket}")
        for entry in by_key.values():
            if entry["bucket"] == bucket:
                selected[entry["name"]] = entry

    # конкретные скиллы
    for token in cfg.get("include", []):
        entry = _match(token, by_key, by_name)
        if entry is None:
            warn(f"include: скилл '{token}' не найден в реестре — пропуск")
            skipped.append(token)
            continue
        selected[entry["name"]] = entry

    # вычитание
    exclude = set(cfg.get("exclude", []))
    if exclude:
        for name, entry in list(selected.items()):
            full = f"{entry['bucket']}/{entry['rel']}".rstrip("/") \
                if entry["rel"] else entry["bucket"]
            if {name, full, entry["bucket"], entry["rel"]} & exclude:
                del selected[name]

    entries = sorted(selected.values(),
                     key=lambda e: (e["bucket"], e["name"]))
    return entries, skipped


# --- lock ---------------------------------------------------------------------
def load_lock(target):
    f = Path(target) / LOCK_FILE
    if not f.is_file():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_lock(target, lock):
    f = Path(target) / LOCK_FILE
    tmp = f.with_name(LOCK_FILE + ".tmp")
    tmp.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, f)


def _dir_sha256(skill_dir):
    """sha256 SKILL.md — та же база, что в реестре (skills.json считает по файлу)."""
    md = Path(skill_dir) / "SKILL.md"
    if not md.is_file():
        return ""
    return hashlib.sha256(md.read_bytes()).hexdigest()


# --- sync ---------------------------------------------------------------------
def plan_sync(env, target, cfg):
    """Сухой расчёт: что добавить/обновить/удалить. Ничего не пишет.

    Возвращает dict: {add, update, remove, keep, conflicts, skills_path, entries}.
    - add:    name'ы новых managed-скиллов
    - update: name'ы managed-скиллов с разошедшимся sha256 (или отсутствующим файлом)
    - remove: name'ы managed-скиллов из lock, которых больше нет в конфиге
    - keep:   managed-скиллы без изменений
    - conflicts: name'ы из add, чей путь занят ЧУЖИМ скиллом (не managed) — symlink/
                 каталог/файл, который мы не ставили. sync без force их пропускает.
    Чужие (managed!=true) записи в расчёте удаления НЕ участвуют."""
    entries, skipped = resolve_skillset(env, cfg)
    skills_path = cfg.get("skills_path") or DEFAULT_SKILLS_PATH
    dest_root = Path(target) / skills_path
    lock = load_lock(target)
    locked = lock.get("skills", {})

    desired = {e["name"]: e for e in entries}
    managed_locked = {n: e for n, e in locked.items() if e.get("managed")}

    add, update, keep, conflicts = [], [], [], []
    for name, entry in desired.items():
        dst = dest_root / name
        prev = managed_locked.get(name)
        if prev is None:
            # новый для нас; если путь занят чужим (не managed) — конфликт
            if dst.is_symlink() or dst.exists():
                conflicts.append(name)
            else:
                add.append(name)
        elif not dst.is_dir() or dst.is_symlink():
            add.append(name)
        elif prev.get("sha256") != entry["sha256"]:
            update.append(name)
        else:
            keep.append(name)
    remove = [n for n in managed_locked if n not in desired]
    return {
        "add": sorted(add), "update": sorted(update),
        "remove": sorted(remove), "keep": sorted(keep),
        "conflicts": sorted(conflicts),
        "skipped": skipped, "skills_path": skills_path,
        "entries": entries, "dest_root": dest_root,
    }


def _remove_path(path):
    """Снести каталог/файл/симлинк по пути (симлинк не разыменовываем)."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def sync_skillset(env, target, cfg, dry_run=False, force=False):
    """Применить конфиг: скопировать новые/обновлённые, удалить выбывшие managed,
    переписать skills-lock.json. Чужие скиллы остаются как есть (конфликты
    пропускаются с warning; --force перетирает чужой путь нашим скиллом)."""
    plan = plan_sync(env, target, cfg)
    dest_root = plan["dest_root"]
    entries = {e["name"]: e for e in plan["entries"]}
    lock = load_lock(target)
    locked = dict(lock.get("skills", {}))

    def contained(path):
        return str(Path(path).resolve()).startswith(
            str(dest_root.resolve()) + os.sep)

    # Конфликты с чужими путями: без force — пропуск; с force — добавить к install.
    install = list(plan["add"]) + list(plan["update"])
    if plan["conflicts"]:
        if force:
            install += plan["conflicts"]
        else:
            for name in plan["conflicts"]:
                warn(f"конфликт: '{name}' занят чужим скиллом (не managed) — "
                     f"пропуск; --force чтобы заменить версией из библиотеки")

    # --- prune: только managed, выбывшие из конфига ---------------------------
    for name in plan["remove"]:
        stale = dest_root / name
        if dry_run:
            print(f"[dry-run] remove {stale}")
        elif (stale.is_symlink() or stale.exists()) and contained(stale):
            _remove_path(stale)
        locked.pop(name, None)

    # --- install / update -----------------------------------------------------
    if not dry_run:
        dest_root.mkdir(parents=True, exist_ok=True)
    for name in install:
        entry = entries[name]
        src = entry["skill_dir"]
        dst = dest_root / name
        if dry_run:
            verb = "add" if name in plan["add"] else \
                ("replace" if name in plan["conflicts"] else "update")
            print(f"[dry-run] {verb} {entry['bucket']}/{entry['name']} -> {dst}")
            continue
        if dst.is_symlink() or dst.exists():
            _remove_path(dst)
        shutil.copytree(src, dst, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("upstream.json",
                                                      ".claude-plugin"))
        locked[name] = {
            "source": SOURCE,
            "managed": True,
            "bucket": entry["bucket"],
            "sha256": _dir_sha256(dst),
            "installed_path": f"{plan['skills_path']}/{name}",
        }

    # keep: освежить метаданные на случай ручной правки lock
    for name in plan["keep"]:
        entry = entries[name]
        locked.setdefault(name, {})
        locked[name].update({
            "source": SOURCE, "managed": True, "bucket": entry["bucket"],
            "sha256": entry["sha256"],
            "installed_path": f"{plan['skills_path']}/{name}",
        })

    new_lock = {
        "version": lock.get("version", LOCK_VERSION),
        "skills": dict(sorted(locked.items())),
        "sources": {**lock.get("sources", {}),
                    SOURCE: {"ref": "registry", "mode": "vendor"}},
    }
    if not dry_run:
        write_lock(target, new_lock)
    return plan


# --- CLI ----------------------------------------------------------------------
def cmd_sync(env, argv):
    opts = parse_flags(argv, {"--target": "str", "--dry-run": "bool",
                              "--force": "bool"})
    if opts["help"]:
        print("swissknifeman sync [--target DIR] [--dry-run] [--force]\n"
              "  Применяет .swissknifeman/config.json (mode=vendor): копирует "
              "скиллы из библиотеки в проект, пишет skills-lock.json (managed) и\n"
              "  удаляет выбывшие managed-скиллы. Чужие скиллы не трогает "
              "(--force перетирает занятый чужим путь версией из библиотеки).")
        return
    target, via = resolve_target(env, opts, allow_home_confirm=True)
    cfg = load_skillset_config(target)
    if cfg is None:
        die(f"{skillset_config_path(target)} не найден — создайте конфиг "
            "vendor-режима (mode=vendor, include/buckets/exclude)")

    plan = sync_skillset(env, target, cfg, dry_run=opts["dry_run"],
                         force=opts["force"])
    prefix = "[dry-run] " if opts["dry_run"] else ""
    n_repl = len(plan["conflicts"]) if opts["force"] else 0
    print(f"{prefix}sync ({via}): +{len(plan['add'])} ~{len(plan['update'])} "
          f"-{len(plan['remove'])} ={len(plan['keep'])}"
          + (f" !{n_repl}" if n_repl else "")
          + f" (skills_path: {plan['skills_path']})")
    if plan["conflicts"] and not opts["force"]:
        print(f"  конфликты (чужие, пропущены): {', '.join(plan['conflicts'])} "
              "— --force чтобы заменить")
    if plan["skipped"]:
        print(f"  пропущено (нет в реестре): {', '.join(plan['skipped'])}")
