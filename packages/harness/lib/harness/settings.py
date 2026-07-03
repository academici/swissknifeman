"""Запись в .claude/.mcp/.swissknife проекта — merge-only, dry-run aware, бэкап *.bak.

Примитивы перенесены из skiller/integrate.py (общие writer'ы окружения): они
не затирают чужое содержимое, делают *.bak и понимают dry-run."""
import json

from .common import atomic_write_text, backup_file, die


def write_json(path, data, dry):
    if dry:
        print(f"  [dry-run] записал бы {path}")
        return
    backup_file(path)
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"  записано: {path}")


def write_text(path, text, dry):
    if dry:
        print(f"  [dry-run] записал бы {path} ({text!r})")
        return
    backup_file(path)
    atomic_write_text(path, text)
    print(f"  записано: {path}")


def load_settings(target, fname):
    f = target / ".claude" / fname
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")), f
        except json.JSONDecodeError as e:
            die(f"{f}: невалидный JSON: {e}")
    return {}, f


def add_hook(settings, event, matcher, command):
    """Добавить PreToolUse/Notification-хук, merge-only. True если добавлен."""
    entries = settings.setdefault("hooks", {}).setdefault(event, [])
    for e in entries:
        if e.get("matcher") == matcher and \
                any(h.get("command") == command for h in e.get("hooks", [])):
            return False
    entry = {"hooks": [{"type": "command", "command": command}]}
    if matcher:
        entry = {"matcher": matcher, **entry}
    entries.append(entry)
    return True


def remove_permission_rules(settings, key, rules):
    """Удалить ТОЧНЫЕ совпадения rules из permissions.<key> (семантика «снимаем
    своё» — чужие правила не трогаем). Возвращает число удалённых."""
    perms = settings.get("permissions")
    if not isinstance(perms, dict) or not isinstance(perms.get(key), list):
        return 0
    kept = [r for r in perms[key] if r not in rules]
    removed = len(perms[key]) - len(kept)
    if removed:
        if kept:
            perms[key] = kept
        else:
            del perms[key]
    return removed


def set_setting_key(target, fname, key, value, dry):
    """Merge-only writer одного top-level ключа в .claude/<fname> (напр. outputStyle). Бэкап *.bak."""
    settings, f = load_settings(target, fname)
    if settings.get(key) == value:
        print(f"  {fname}:{key} уже = {value}")
        return
    settings[key] = value
    write_json(f, settings, dry)


def set_swissknife(target, key, value, dry):
    f = target / ".swissknife.json"
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{f}: невалидный JSON: {e}")
    if data.get(key) == value:
        print(f"  .swissknife.json:{key} уже = {value}")
        return
    data[key] = value
    write_json(f, data, dry)
