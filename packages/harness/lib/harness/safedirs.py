"""Internal documentation."""
import importlib.util
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .common import die, find_monorepo_root, parse_args, safe_load_json, warn
from .settings import load_settings, remove_permission_rules, write_json

SUBCOMMANDS = ("init", "list", "add", "remove", "prune-ask", "delete")



PRUNE_ASK_RULES = ("Bash(rm -r *)", "Bash(rm -rf *)")

DEFAULT_CONFIG = {
    "version": 1,
    "include_registered_projects": True,
    "dirs": [],
    "exclude": [],
    "protect_git": True,
    "allow_globs": True,
}


def _state_file(env):
    """Internal documentation."""
    override = os.environ.get("SKM_SAFE_DIRS_CONFIG")
    if override:
        return Path(override)
    root = find_monorepo_root(env.root)
    if root:
        return root / "safe-dirs.json"
    return env.home / ".swissknifeman" / "safe-dirs.json"


def _legacy_file(env):
    return env.home / ".swissknifeman" / "safe-dirs.json"


def _hook_module(env):
    """Internal documentation."""
    path = (env.configs_dir / "hooks" / "auto-approve" / "lib" / "safedirs.py")
    spec = importlib.util.spec_from_file_location("hook_safedirs", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_config(env):
    f = _state_file(env)
    if not f.exists():
        die(f"нет {f} — сначала: harness safe-dirs init")
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{f}: невалидный JSON: {e}")
    if not isinstance(cfg, dict) or cfg.get("version") != 1:
        die(f"{f}: неизвестный формат (version != 1)")
    return cfg, f


def _validate_root(env, raw):
    """Internal documentation."""
    mod = _hook_module(env)
    home = str(env.home)
    resolved = mod._norm_root(raw, home, str(Path(home).resolve()))
    if resolved is None:
        die(f"недопустимый корень: {raw!r} — нужен абсолютный (или ~/) путь, "
            "не '/', не $HOME и не предок $HOME")
    return resolved


def cmd_init(env, opts):
    f = _state_file(env)
    if f.exists():
        print(f"уже существует: {f}")
        return
    legacy = _legacy_file(env)
    if legacy.exists() and legacy != f:


        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{legacy}: невалидный JSON, миграция невозможна: {e}")
        write_json(f, data, opts["dry_run"])
        if not opts["dry_run"]:
            legacy.rename(legacy.with_suffix(".json.migrated"))
        print(f"  мигрировано из legacy: {legacy} → {f} "
              f"(старый файл сохранён как {legacy.name}.migrated)")
        return
    write_json(f, DEFAULT_CONFIG, opts["dry_run"])
    print("  дефолт: include_registered_projects=true (реестр ~/.swissknifeman/"
          "projects.json); явные корни — harness safe-dirs add <path>")


def cmd_list(env, _opts):
    cfg, f = _load_config(env)
    mod = _hook_module(env)
    allow = mod.load_allowlist(str(env.home), str(f))
    print(f"конфиг: {f}")
    if allow is None:
        warn("конфиг не грузится глазами хука — фича ВЫКЛЮЧЕНА (rm блокируется как раньше)")
        return
    print(f"  include_registered_projects={cfg.get('include_registered_projects')}, "
          f"protect_git={allow['protect_git']}, allow_globs={allow['allow_globs']}")
    print(f"эффективные корни ({len(allow['roots'])}):")
    for r in allow["roots"]:
        print(f"  {r}")
    if not allow["roots"]:
        print("  (пусто — rm везде блокируется, добавь: harness safe-dirs add <path>)")
    if allow["excludes"]:
        print(f"изъятия ({len(allow['excludes'])}):")
        for e in allow["excludes"]:
            print(f"  {e}")


def cmd_add(env, opts, raw):
    cfg, f = _load_config(env)
    key = "exclude" if opts["exclude"] else "dirs"
    if key == "dirs":
        resolved = _validate_root(env, raw)
    else:
        mod = _hook_module(env)
        resolved = mod._abs_real(raw, str(env.home))
        if resolved is None:
            die(f"недопустимое изъятие: {raw!r} — нужен абсолютный (или ~/) путь")
    entries = cfg.setdefault(key, [])
    mod = _hook_module(env)
    existing = [mod._abs_real(x, str(env.home)) for x in entries]
    if resolved in existing:
        print(f"уже в {key}: {raw} ({resolved})")
        return
    entries.append(raw)
    write_json(f, cfg, opts["dry_run"])
    print(f"  добавлено в {key}: {raw} → {resolved}")


def cmd_remove(env, opts, raw):
    cfg, f = _load_config(env)
    key = "exclude" if opts["exclude"] else "dirs"
    mod = _hook_module(env)
    target = mod._abs_real(raw, str(env.home))
    entries = cfg.get(key) or []
    kept = [x for x in entries if mod._abs_real(x, str(env.home)) != target]
    if len(kept) == len(entries):
        die(f"не найдено в {key}: {raw}")
    cfg[key] = kept
    write_json(f, cfg, opts["dry_run"])
    print(f"  убрано из {key}: {raw}")


def _prune_one(target_dir, fname, dry):
    """Internal documentation."""
    f = Path(target_dir) / ".claude" / fname
    if not f.exists():
        return 0
    settings, f = load_settings(Path(target_dir), fname)
    removed = remove_permission_rules(settings, "ask", PRUNE_ASK_RULES)
    if removed:
        write_json(f, settings, dry)
        print(f"  {f}: снято ask-правил rm: {removed}")
    return removed


def cmd_prune_ask(env, opts):
    if not (opts["global"] or opts["target"] or opts["all_projects"]):
        die("нужен хотя бы один из: --global / --target P / --all-projects")
    total = 0
    if opts["global"]:
        total += _prune_one(env.home, "settings.json", opts["dry_run"])
    targets = []
    if opts["target"]:
        targets.append(Path(opts["target"]).expanduser())
    if opts["all_projects"]:
        reg = safe_load_json(env.home / ".swissknifeman" / "projects.json", {}) or {}
        targets += [Path(p["path"]) for p in reg.get("projects", [])
                    if isinstance(p, dict) and isinstance(p.get("path"), str)]
    for t in targets:
        if not t.is_dir():
            warn(f"пропуск (нет каталога): {t}")
            continue
        for fname in ("settings.json", "settings.local.json"):
            total += _prune_one(t, fname, opts["dry_run"])
    print(f"итого снято правил: {total}" if total else
          "ask-правила rm не найдены — чисто")


_FORBIDDEN_CHARS = ("$", "`", "{", "}", "*", "?", "[")


def _log_delete(log_file, raw, resolved, result, dry_run):
    """Internal documentation."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw": raw, "resolved": resolved, "result": result, "dry_run": dry_run,
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cmd_delete(env, opts, paths):
    """Internal documentation."""
    if not paths:
        die("нужен хотя бы один путь: harness safe-dirs delete <path> [<path> …] [--dry-run]")
    cfg, f = _load_config(env)
    mod = _hook_module(env)
    allow = mod.load_allowlist(str(env.home), str(f))
    if allow is None:
        die("конфиг safe-dirs не грузится глазами хука — сначала: harness safe-dirs init")
    home = str(env.home)
    log_file = env.home / ".claude" / "logs" / "safe-delete-decisions.jsonl"
    resolved = []
    for raw in paths:
        if any(ch in raw for ch in _FORBIDDEN_CHARS):
            die(f"недопустимый путь (глобы/подстановки запрещены — только "
                f"конкретный файл/папка): {raw!r}")
        if ".." in raw.split("/"):
            die(f"недопустимый путь (компонент '..'): {raw!r}")
        p = mod._abs_real(raw, home)
        if p is None:
            die(f"путь должен быть абсолютным (или ~/подпуть): {raw!r}")
        if not mod._contained(p, allow, allow_root=False):
            die(f"вне доверенного дерева (safe-dirs.json) — отказ: {raw!r} → {p}")
        resolved.append((raw, p))
    for raw, p in resolved:
        exists = os.path.lexists(p)
        if not exists:
            print(f"  пропуск (уже отсутствует): {raw}")
            _log_delete(log_file, raw, p, "skip-absent", opts["dry_run"])
            continue
        if opts["dry_run"]:
            print(f"  [dry-run] удалил бы: {raw} → {p}")
            _log_delete(log_file, raw, p, "dry-run", True)
            continue
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        except OSError as e:
            _log_delete(log_file, raw, p, f"error: {e}", False)
            die(f"ошибка удаления {raw} ({p}): {e}")
        print(f"  удалено: {raw} → {p}")
        _log_delete(log_file, raw, p, "deleted", False)


def cmd_safedirs(env, argv):
    opts, pos = parse_args(argv, {
        "--exclude": "bool", "--global": "bool", "--target": "str",
        "--all-projects": "bool", "--dry-run": "bool",
    }, max_pos=64)
    if opts["help"] or not pos:
        print("harness safe-dirs <init|list|add|remove|prune-ask|delete>\n"
              "  init                          создать ~/.swissknifeman/safe-dirs.json\n"
              "  list                          эффективный allowlist глазами хука\n"
              "  add <path> [--exclude]        добавить корень (или изъятие)\n"
              "  remove <path> [--exclude]     убрать корень (или изъятие)\n"
              "  prune-ask [--global] [--target P] [--all-projects]\n"
              "                                снять ask-правила rm из settings\n"
              "  delete <path> [<path> …]      удалить напрямую (эскейп-хетч для\n"
              "                                for/xargs/sudo-заблокированных rm)\n"
              "Общее: [--dry-run]")
        return
    sub = pos[0]
    if sub not in SUBCOMMANDS:
        die(f"неизвестная подкоманда: {sub} ({'|'.join(SUBCOMMANDS)})")
    if sub in ("add", "remove"):
        if len(pos) < 2:
            die(f"нужен путь: harness safe-dirs {sub} <path>")
        (cmd_add if sub == "add" else cmd_remove)(env, opts, pos[1])
        return
    if sub == "delete":
        cmd_delete(env, opts, pos[1:])
        return
    if len(pos) > 1:
        die(f"лишний аргумент: {pos[1]}")
    if sub == "init":
        cmd_init(env, opts)
    elif sub == "list":
        cmd_list(env, opts)
    else:
        cmd_prune_ask(env, opts)
