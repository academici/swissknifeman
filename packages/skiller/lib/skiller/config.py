"""Project config (.swissknife.json), профили и выбор скиллов/плагинов."""
import json
import os
from pathlib import Path

from core import detect_project_type

from .common import (AGENT_DEFAULTS, CONFIG_KEYS, confirm, die,
                     parse_frontmatter_fields, warn)

# CORE-политика раздачи: токен-экономные скиллы, которые swissknifeman кладёт в
# КАЖДЫЙ проект по умолчанию (см. deep_analysis §5–§6). Каналы разной гранулярности:
#   connect (marketplace) — bucket-granular → CORE_BUCKETS;
#   vendor (физ. копия)    — skill-granular → CORE_SKILLS + DEFAULT_EXCLUDE.
# DEFAULT_EXCLUDE убирает из авто-раздачи скиллы, дублирующие хаб maind
# (shared-memory ← agent-memory MCP) и ручные инструменты (cross-project-coordinator).
# Отключается флагом --no-core у connect/vendor.
CORE_SKILLS = [
    "general/context-economy", "general/anti-drift", "general/compact-responses",
    "general/session-handoff", "general/mcp-advisor", "oss-dev/gh-review",
]
CORE_BUCKETS = ["general", "oss-dev"]
DEFAULT_EXCLUDE = ["system/shared-memory", "system/cross-project-coordinator"]
# Минимальный безопасный набор для НЕРАСПОЗНАННОГО типа проекта (autodetect → standalone).
# НЕ разворачиваем `["*"]` (= все бакеты) по умолчанию — это «бездушный дамп всего». Явный
# `--profile standalone` («поставь всё») остаётся доступен; авто-фолбэк ставит только ядро.
MINIMAL_BUCKETS = ["general", "oss-dev", "system"]


def core_skill_tuples(env, exclude):
    """CORE_SKILLS → [(bucket, rel, dir, fm_name)]; пропускает excluded и
    отсутствующие. Формат кортежа совпадает с vendor.collect_skills."""
    out = []
    for path in CORE_SKILLS:
        bucket, _, rel = path.partition("/")
        d = env.root / "skills" / bucket / rel
        md = d / "SKILL.md"
        if not md.is_file():
            continue
        fm_name = parse_frontmatter_fields(md)["name"]
        if {fm_name, d.name, path} & exclude:
            continue
        out.append((bucket, rel, d, fm_name))
    return out


def validate_config(env, config, cfg_file):
    import difflib
    profile_names = sorted(p.stem for p in (env.root / "profiles").glob("*.json"))
    for key, value in config.items():
        if key.startswith(("_", "$")):  # _comment / $schema — DX, не валидируем
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
    # skills_map объявлен в CONFIG_KEYS, но ещё не читается логикой — не молчим,
    # иначе пользователь пропишет его и не поймёт, почему нет эффекта.
    if config.get("skills_map"):
        warn(f"{cfg_file}: 'skills_map' зарезервирован, но ещё не реализован "
             f"— игнорируется")


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
    """Тип проекта (== имя профиля) — единый детектор core. Каждый возвращаемый id
    обязан иметь profiles/<id>.json (гейт покрытия в validate.sh)."""
    return detect_project_type(target)


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
    # Тип не распознан (фолбэк-профиль standalone = `["*"]`) → НЕ ставим всё подряд:
    # отдаём минимальное ядро и маркер источника `autodetect-fallback`, чтобы вызывающий
    # (connect/vendor) предупредил и предложил указать профиль явно. Явный `--profile
    # standalone` сюда не попадает (обрабатывается веткой flag_profile выше).
    if prof["buckets"] == ["*"]:
        items = [b for b in MINIMAL_BUCKETS if b in buckets]
        return items, name, "autodetect-fallback", "autodetect-fallback", False
    return prof["buckets"], name, "autodetect", "autodetect", prof.get("include_meta", False)


def resolve_profile_name(target, config, flag_profile):
    """Имя профиля по той же иерархии, что resolve_selection: --profile >
    .swissknife.json project_type > autodetect. None — если выбор задан явными
    buckets (профиля нет)."""
    if flag_profile:
        return flag_profile
    if config.get("buckets"):
        return None
    if config.get("project_type"):
        return config["project_type"]
    return autodetect(target)


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
        if (p / ".swissknifeman" / "config.json").is_file():
            return p, ".swissknifeman/config.json"
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
    if target == env.root.resolve() and env.cmd in ("connect", "vendor", "update", "sync", "init"):
        die("вы внутри самого реестра swissknifeman — перейдите в "
            "потребляющий проект")
    return target, via
