"""Project config (.swissknife.json), профили и выбор скиллов/плагинов."""
import json
import os
from pathlib import Path

from .common import (AGENT_DEFAULTS, CONFIG_KEYS, Env, confirm, die)


def validate_config(env, config, cfg_file):
    import difflib
    profile_names = sorted(p.stem for p in (env.root / "profiles").glob("*.json"))
    for key, value in config.items():
        if key.startswith("_"):
            continue
        if key not in CONFIG_KEYS:
            hint = difflib.get_close_matches(key, CONFIG_KEYS, n=1)
            suffix = f" — did you mean '{hint[0]}'?" if hint else ""
            die(f"{cfg_file}: unknown key '{key}'{suffix}")
        if not isinstance(value, CONFIG_KEYS[key]):
            die(f"{cfg_file}: '{key}' must be a "
                f"{'list of strings' if CONFIG_KEYS[key] is list else 'string'}")
        if CONFIG_KEYS[key] is list and not all(isinstance(v, str) for v in value):
            die(f"{cfg_file}: '{key}' must be a list of strings")
    if config.get("project_type") and config["project_type"] not in profile_names:
        die(f"{cfg_file}: unknown project_type '{config['project_type']}' "
            f"(available: {', '.join(profile_names)})")
    if config.get("agent") and config["agent"] not in AGENT_DEFAULTS:
        die(f"{cfg_file}: unknown agent '{config['agent']}' "
            f"(available: {', '.join(AGENT_DEFAULTS)})")


def load_config(env, target):
    cfg_file = target / ".swissknife.json"
    if not cfg_file.exists():
        return {}
    try:
        config = json.loads(cfg_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{cfg_file}: invalid JSON: {e}")
    validate_config(env, config, cfg_file)
    return config


def autodetect(target):
    if (target / ".obsidian").is_dir():
        return "obsidian-vault"
    if (target / "artisan").is_file() and (target / "composer.json").is_file():
        return "laravel-project"
    if (target / "composer.json").is_file():
        return "php-package"
    return "standalone"


def load_profile(env, name):
    f = env.root / "profiles" / f"{name}.json"
    if not f.exists():
        available = ", ".join(
            sorted(p.stem for p in (env.root / "profiles").glob("*.json")))
        die(f"unknown profile '{name}' (available: {available})")
    return json.loads(f.read_text(encoding="utf-8"))


def all_buckets(env):
    return sorted(d.name for d in (env.root / "skills").iterdir() if d.is_dir())


def resolve_selection(env, target, config, flag_profile, flag_items):
    """Shared precedence: flags > .swissknife.json > autodetect.
    Returns (items, profile_name, profile_source, source_label, include_meta)."""
    buckets = all_buckets(env)
    if flag_items:
        return flag_items, None, "items", "flags", False
    if flag_profile:
        prof = load_profile(env, flag_profile)
        items = buckets if prof["buckets"] == ["*"] else prof["buckets"]
        return items, flag_profile, "flag", "--profile", prof.get("include_meta", False)
    if config.get("buckets"):
        return config["buckets"], None, "config", ".swissknife.json buckets", False
    if config.get("project_type"):
        prof = load_profile(env, config["project_type"])
        items = buckets if prof["buckets"] == ["*"] else prof["buckets"]
        return (items, config["project_type"], "config",
                ".swissknife.json project_type", prof.get("include_meta", False))
    name = autodetect(target)
    prof = load_profile(env, name)
    items = buckets if prof["buckets"] == ["*"] else prof["buckets"]
    return items, name, "autodetect", "autodetect", prof.get("include_meta", False)


# --- project root discovery ----------------------------------------------------
def find_project_root(env, start=None):
    """Nearest dir upward containing .swissknife.json, .claude/ or .git."""
    p = (start or Path.cwd()).resolve()
    home = env.home.resolve()
    while True:
        if str(p) == p.root:
            return None, None
        if (p / ".swissknife.json").is_file():
            return p, ".swissknife.json"
        if (p / ".claude").is_dir():
            return p, ".claude/"
        if (p / ".git").exists():  # dir or file (worktree/submodule)
            return p, ".git"
        if p == home:
            return None, None
        p = p.parent


def resolve_target(env, opts, allow_home_confirm=False):
    """--target wins; otherwise walk up from CWD. Refuses the registry repo."""
    if opts.get("target"):
        target = Path(os.path.expanduser(opts["target"])).resolve()
        if not target.is_dir():
            die(f"каталог не найден: {target}")
        via = "--target"
    else:
        target, via = find_project_root(env)
        if target is None:
            die("корень проекта не найден выше CWD (искал .swissknife.json, "
                ".claude/, .git). Перейдите в проект или создайте "
                ".swissknife.json в его корне.")
        if target == env.home.resolve() and allow_home_confirm:
            print("Корень проекта определился как домашняя директория.")
            if not confirm(f"Продолжить с {target}?"):
                die("отменено — перейдите в проект или укажите --target")
    if target == env.root.resolve() and env.cmd in ("connect", "vendor", "update"):
        die("вы внутри самого реестра swissknifeman — перейдите в "
            "потребляющий проект")
    return target, via
