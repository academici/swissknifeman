#!/usr/bin/env bash
# connect-claude.sh — подключает swissknifeman к проекту через нативный
# plugin marketplace Claude Code (вместо вендоринга скиллов install.sh).
#
# Записывает в .claude/settings.local.json целевого проекта:
#   extraKnownMarketplaces.swissknifeman  (source: directory, путь к этому репо)
#   enabledPlugins."<bucket>@swissknifeman"  (по профилю проекта)
#
# Использование:
#   ./scripts/connect-claude.sh --target ~/projects/my-app            # автодетект профиля
#   ./scripts/connect-claude.sh --target . --profile laravel-project  # явный профиль
#   ./scripts/connect-claude.sh --target . --plugins php,quality      # явный список плагинов
#   ./scripts/connect-claude.sh --target . --list                     # показать без записи
#   ./scripts/connect-claude.sh --target . --dry-run                  # итоговый JSON без записи
#   ./scripts/connect-claude.sh --target . --cleanup-vendored         # удалить старые вендоренные копии
#   ./scripts/connect-claude.sh --target . --file settings.json       # в шаримый settings.json
#
# Merge-семантика: только добавляет отсутствующие ключи. Явный false в
# enabledPlugins не перетирается; ранее включённые плагины не отключаются
# (расхождение с профилем только репортится). Бэкап в *.bak.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//' | sed -n '2,20p'; exit "${1:-0}"; }

TARGET=""
PROFILE=""
PLUGINS=""
SETTINGS_FILE="settings.local.json"
CLEANUP=false
LIST=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --plugins) PLUGINS="$2"; shift 2 ;;
    --file) SETTINGS_FILE="$2"; shift 2 ;;
    --cleanup-vendored) CLEANUP=true; shift ;;
    --list) LIST=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage 1 ;;
  esac
done

[[ -n "$TARGET" ]] || { echo "Ошибка: --target обязателен" >&2; usage 1; }
[[ -d "$TARGET" ]] || { echo "Ошибка: каталог не найден: $TARGET" >&2; exit 1; }
case "$SETTINGS_FILE" in
  settings.json|settings.local.json) ;;
  *) echo "Ошибка: --file должен быть settings.json или settings.local.json" >&2; exit 1 ;;
esac

export SKM_TARGET="$TARGET" SKM_PROFILE="$PROFILE" SKM_PLUGINS="$PLUGINS" \
       SKM_SETTINGS_FILE="$SETTINGS_FILE" SKM_CLEANUP="$CLEANUP" \
       SKM_LIST="$LIST" SKM_DRY_RUN="$DRY_RUN"

python3 - "$REPO_ROOT" <<'PY'
import json, os, shutil, sys
from pathlib import Path

root = Path(sys.argv[1])
target = Path(os.path.expanduser(os.environ["SKM_TARGET"])).resolve()
flag_profile = os.environ["SKM_PROFILE"]
flag_plugins = [p for p in os.environ["SKM_PLUGINS"].split(",") if p]
settings_file = os.environ["SKM_SETTINGS_FILE"]
cleanup = os.environ["SKM_CLEANUP"] == "true"
list_only = os.environ["SKM_LIST"] == "true"
dry_run = os.environ["SKM_DRY_RUN"] == "true"

MARKETPLACE = "swissknifeman"
MANIFEST = ".swissknifeman-manifest.json"
AGENT_DEFAULTS = {"claude": ".claude/skills", "cursor": ".cursor/skills",
                  "generic": ".ai/skills"}
CONFIG_KEYS = {
    "project_type": str, "buckets": list, "exclude": list,
    "skills_path": str, "agent": str,
}


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def validate_config(config, cfg_file, profiles_dir):
    """Schema check for .swissknife.json; keys starting with _ are comments."""
    import difflib
    profile_names = sorted(p.stem for p in profiles_dir.glob("*.json"))
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


def autodetect():
    if (target / ".obsidian").is_dir():
        return "obsidian-vault"
    if (target / "artisan").is_file() and (target / "composer.json").is_file():
        return "laravel-project"
    if (target / "composer.json").is_file():
        return "php-package"
    return "standalone"


def load_profile(name):
    f = root / "profiles" / f"{name}.json"
    if not f.exists():
        available = ", ".join(sorted(p.stem for p in (root / "profiles").glob("*.json")))
        die(f"unknown profile '{name}' (available: {available})")
    return json.loads(f.read_text(encoding="utf-8"))


# --- 1. resolve plugins (= buckets + optional generate-skill) ----------------
config = {}
cfg_file = target / ".swissknife.json"
if cfg_file.exists():
    try:
        config = json.loads(cfg_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{cfg_file}: invalid JSON: {e}")
    validate_config(config, cfg_file, root / "profiles")

all_buckets = sorted(d.name for d in (root / "skills").iterdir() if d.is_dir())

profile_name = None
include_meta = False
if flag_plugins:
    plugins, source = flag_plugins, "--plugins"
elif flag_profile:
    prof = load_profile(flag_profile)
    profile_name, source = flag_profile, "--profile"
    plugins = all_buckets if prof["buckets"] == ["*"] else prof["buckets"]
    include_meta = prof.get("include_meta", False)
elif config.get("buckets"):
    plugins, source = config["buckets"], ".swissknife.json buckets"
elif config.get("project_type"):
    prof = load_profile(config["project_type"])
    profile_name, source = config["project_type"], ".swissknife.json project_type"
    plugins = all_buckets if prof["buckets"] == ["*"] else prof["buckets"]
    include_meta = prof.get("include_meta", False)
else:
    profile_name, source = autodetect(), "autodetect"
    prof = load_profile(profile_name)
    plugins = all_buckets if prof["buckets"] == ["*"] else prof["buckets"]
    include_meta = prof.get("include_meta", False)

known_plugins = set(all_buckets) | {"generate-skill"}
for p in plugins:
    if p not in known_plugins:
        die(f"unknown plugin: {p} (available: {', '.join(sorted(known_plugins))})")
if include_meta and "generate-skill" not in plugins:
    plugins = list(plugins) + ["generate-skill"]
plugins = sorted(set(plugins))

if config.get("exclude"):
    print("NOTE: .swissknife.json 'exclude' is skill-granular and is ignored "
          "in plugin mode (plugins are bucket-granular)")

print(f"Target:   {target}")
print(f"Profile:  {profile_name or '-'} (via {source})")
print(f"Source:   {root}")
print(f"Plugins:  {' '.join(plugins)}")

if list_only:
    sys.exit(0)

# --- 2. merge into .claude/<settings_file> -----------------------------------
dest = target / ".claude" / settings_file
settings = {}
if dest.exists():
    try:
        settings = json.loads(dest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{dest}: invalid JSON: {e}")

marketplaces = settings.setdefault("extraKnownMarketplaces", {})
if MARKETPLACE in marketplaces:
    existing = marketplaces[MARKETPLACE].get("source", {})
    if existing != {"source": "directory", "path": str(root)}:
        print(f"NOTE: marketplace '{MARKETPLACE}' already declared with a "
              f"different source — keeping it: {json.dumps(existing)}")
else:
    marketplaces[MARKETPLACE] = {
        "source": {"source": "directory", "path": str(root)}}

enabled = settings.setdefault("enabledPlugins", {})
added, skipped_false = [], []
for p in plugins:
    key = f"{p}@{MARKETPLACE}"
    if key not in enabled:
        enabled[key] = True
        added.append(p)
    elif enabled[key] is False:
        skipped_false.append(p)
drift = [k for k, v in enabled.items()
         if k.endswith(f"@{MARKETPLACE}") and v
         and k.split("@")[0] not in plugins]

if dry_run:
    print(f"--- dry-run: {dest} ---")
    print(json.dumps(settings, ensure_ascii=False, indent=2))
else:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.copy2(dest, f"{dest}.bak")
        print(f"Бэкап:    {dest}.bak")
    dest.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"Записано: {dest}")

if added:
    print(f"Включены: {' '.join(added)}")
if skipped_false:
    print(f"Пропущены (явный false): {' '.join(skipped_false)}")
if drift:
    print(f"NOTE: включены сверх профиля (не трогаю): {' '.join(drift)}")

# --- 3. vendored-copy migration ----------------------------------------------
skills_path = config.get("skills_path") or AGENT_DEFAULTS["claude"]
manifest_file = target / skills_path / MANIFEST
if manifest_file.exists():
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    dest_root = manifest_file.parent
    stale = []
    for entry in manifest.get("skills", []):
        name = entry.get("flat_name") or entry.get("path", "")
        d = dest_root / name
        if name and d.is_dir() and \
                str(d.resolve()).startswith(str(dest_root.resolve()) + os.sep):
            stale.append(d)
    if cleanup and not dry_run:
        for d in stale:
            shutil.rmtree(d)
        manifest_file.unlink()
        print(f"Удалены вендоренные копии: {len(stale)} skill dir(s) + манифест")
    else:
        print(f"NOTE: найдены вендоренные копии ({len(stale)} dir(s) в "
              f"{dest_root}) — удалить: --cleanup-vendored")

print("Далее: перезапустите сессию Claude Code в проекте "
      "(или /plugin marketplace update swissknifeman)")
PY
