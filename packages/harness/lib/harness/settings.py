"""Internal documentation."""
import json

from .common import atomic_write_text, backup_file, die


def write_json(path, data, dry):
    if dry:
        print(f"  [dry-run] would write {path}")
        return
    backup_file(path)
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"  written: {path}")


def write_text(path, text, dry):
    if dry:
        print(f"  [dry-run] would write {path} ({text!r})")
        return
    backup_file(path)
    atomic_write_text(path, text)
    print(f"  written: {path}")


def load_settings(target, fname):
    f = target / ".claude" / fname
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")), f
        except json.JSONDecodeError as e:
            die(f"{f}: invalid JSON: {e}")
    return {}, f


def add_hook(settings, event, matcher, command):
    """Internal documentation."""
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
    """Internal documentation."""
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
    """Internal documentation."""
    settings, f = load_settings(target, fname)
    if settings.get(key) == value:
        print(f"  {fname}:{key} already = {value}")
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
            die(f"{f}: invalid JSON: {e}")
    if data.get(key) == value:
        print(f"  .swissknife.json:{key} already = {value}")
        return
    data[key] = value
    write_json(f, data, dry)
