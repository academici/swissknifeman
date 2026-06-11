#!/usr/bin/env bash
# apply-permissions.sh — вливает пресеты permissions из configs/claude-code/
# в .claude/settings.local.json целевого проекта.
#
# Использование:
#   ./scripts/apply-permissions.sh --target ~/projects/my-app                 # base + автодетект стека
#   ./scripts/apply-permissions.sh --target . --preset base,laravel,docker    # явный список
#   ./scripts/apply-permissions.sh --target . --list                          # доступные пресеты
#   ./scripts/apply-permissions.sh --target . --dry-run                       # показать без записи
#   ./scripts/apply-permissions.sh --target . --file settings.json            # в шаримый settings.json
#
# Merge-семантика: allow/ask/deny объединяются и дедуплицируются, существующие
# правила цели сохраняются. defaultMode берётся из пресета только если в цели
# он ещё не задан. Существующий файл сохраняется в *.bak.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRESETS_DIR="$SCRIPT_DIR/../configs/claude-code"

TARGET=""
PRESETS=""
SETTINGS_FILE="settings.local.json"
DRY_RUN=0

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -14; exit "${1:-0}"; }

list_presets() {
  echo "Доступные пресеты (configs/claude-code/):"
  for f in "$PRESETS_DIR"/settings.*.json; do
    basename "$f" | sed -E 's/^settings\.(.+)\.json$/  \1/'
  done
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)  TARGET="$2"; shift 2 ;;
    --preset)  PRESETS="$2"; shift 2 ;;
    --file)    SETTINGS_FILE="$2"; shift 2 ;;
    --list)    list_presets ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage 1 ;;
  esac
done

[[ -n "$TARGET" ]] || { echo "Ошибка: --target обязателен" >&2; usage 1; }
[[ -d "$TARGET" ]] || { echo "Ошибка: каталог не найден: $TARGET" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"

# Автодетект стека — та же логика маркеров, что в install.sh
detect_presets() {
  local detected="base"
  if [[ -f "$TARGET/artisan" && -f "$TARGET/composer.json" ]]; then
    detected+=",laravel"
  elif [[ -f "$TARGET/composer.json" ]]; then
    detected+=",php-package"
  fi
  if [[ -f "$TARGET/package.json" ]]; then
    detected+=",node"
  fi
  if [[ -f "$TARGET/pyproject.toml" || -f "$TARGET/requirements.txt" ]]; then
    detected+=",python"
  fi
  if [[ -f "$TARGET/compose.yaml" || -f "$TARGET/compose.yml" || -f "$TARGET/docker-compose.yml" || -f "$TARGET/Dockerfile" ]]; then
    detected+=",docker"
  fi
  echo "$detected"
}

[[ -n "$PRESETS" ]] || { PRESETS="$(detect_presets)"; echo "Автодетект: $PRESETS"; }

PRESET_FILES=()
IFS=',' read -ra NAMES <<< "$PRESETS"
for name in "${NAMES[@]}"; do
  f="$PRESETS_DIR/settings.${name}.json"
  [[ -f "$f" ]] || { echo "Ошибка: пресет не найден: $name ($f)" >&2; exit 1; }
  PRESET_FILES+=("$f")
done

DEST_DIR="$TARGET/.claude"
DEST="$DEST_DIR/$SETTINGS_FILE"

MERGED="$(python3 - "$DEST" "${PRESET_FILES[@]}" <<'PY'
import json, os, sys

dest_path, preset_paths = sys.argv[1], sys.argv[2:]

def load(path):
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {}

result = load(dest_path)
perms = result.setdefault("permissions", {})

for path in preset_paths:
    preset = load(path).get("permissions", {})
    for key in ("allow", "ask", "deny"):
        merged = perms.get(key, []) + [r for r in preset.get(key, [])
                                       if r not in perms.get(key, [])]
        if merged:
            perms[key] = merged
    if "defaultMode" in preset and "defaultMode" not in perms:
        perms["defaultMode"] = preset["defaultMode"]

print(json.dumps(result, ensure_ascii=False, indent=2))
PY
)"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "--- dry-run: $DEST ---"
  echo "$MERGED"
  exit 0
fi

mkdir -p "$DEST_DIR"
[[ -f "$DEST" ]] && cp "$DEST" "$DEST.bak"
printf '%s\n' "$MERGED" > "$DEST"
echo "Записано: $DEST (пресеты: $PRESETS)"
if [[ -f "$DEST.bak" ]]; then echo "Бэкап:    $DEST.bak"; fi
