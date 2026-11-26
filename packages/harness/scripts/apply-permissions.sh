#!/usr/bin/env bash
#
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRESETS_DIR="$SCRIPT_DIR/../configs/claude-code"
RG_OLD_STUB_SHA256="2ba2ef6564d8dcb5591b691667ce00d137510cc60c42b185f0ef5d3e1aeb22d2"

TARGET=""
PRESETS=""
SETTINGS_FILE="settings.local.json"
DRY_RUN=0
GLOBAL=0

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -15; exit "${1:-0}"; }

list_presets() {
  echo "Available presets (configs/claude-code/):"
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
    --global)  GLOBAL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown argument: $1" >&2; usage 1 ;;
  esac
done

if [[ "$GLOBAL" -eq 1 ]]; then
  TARGET="$HOME"
  SETTINGS_FILE="settings.json"
  PRESETS="${PRESETS:-global}"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    mkdir -p "$HOME/.claude/hooks/auto-approve"
    cp "$PRESETS_DIR/hooks/log-bash-command.sh" "$HOME/.claude/hooks/"
    chmod +x "$HOME/.claude/hooks/log-bash-command.sh"
    mkdir -p "$HOME/.claude/hooks/notify"
    cp "$PRESETS_DIR/hooks/notify/notify.sh" "$HOME/.claude/hooks/notify/"
    chmod +x "$HOME/.claude/hooks/notify/notify.sh"
    mkdir -p "$HOME/.claude/hooks/daemon-safety"
    cp "$PRESETS_DIR/hooks/daemon-safety/block-daemon-ops.sh" "$HOME/.claude/hooks/daemon-safety/"
    chmod +x "$HOME/.claude/hooks/daemon-safety/block-daemon-ops.sh"
    RG_SRC="$PRESETS_DIR/hooks/review-gate"; RG_DST="$HOME/.claude/hooks/review-gate"
    mkdir -p "$RG_DST/checks"
    cp "$RG_SRC/review-gate.sh" "$RG_DST/"
    cp "$RG_SRC/README.md" "$RG_DST/"
    cp "$RG_SRC/checks/"*.sh "$RG_DST/checks/"
    chmod +x "$RG_DST/review-gate.sh" "$RG_DST/checks/"*.sh
    [[ -f "$RG_DST/env.ini" ]] || cp "$RG_SRC/env.ini" "$RG_DST/"
    if [[ ! -f "$RG_DST/config.json" ]]; then
      cp "$RG_SRC/config.json" "$RG_DST/"
    else
      RG_DST_SHA256="$(sha256sum "$RG_DST/config.json" | cut -d' ' -f1)"
      if [[ "$RG_DST_SHA256" == "$RG_OLD_STUB_SHA256" ]]; then
        cp "$RG_SRC/config.json" "$RG_DST/"
      else
        echo "review-gate: $RG_DST/config.json — not an old stub (respect local choice I don't touch), "
        echo "  Update manually: cp \"$RG_SRC/config.json\" \"$RG_DST/config.json\""
      fi
    fi
    SL_SRC="$PRESETS_DIR/statusline"; SL_DST="$HOME/.claude/statusline"
    mkdir -p "$SL_DST"
    cp "$SL_SRC/context-notify.sh" "$SL_DST/"
    cp "$SL_SRC/README.md" "$SL_DST/"
    chmod +x "$SL_DST/context-notify.sh"
    [[ -f "$SL_DST/env.ini" ]] || cp "$SL_SRC/env.ini" "$SL_DST/"
    OB_SRC="$PRESETS_DIR/hooks/observer"; OB_DST="$HOME/.claude/hooks/observer"
    mkdir -p "$OB_DST"
    cp "$OB_SRC/observer.sh" "$OB_DST/"
    cp "$OB_SRC/README.md" "$OB_DST/"
    chmod +x "$OB_DST/observer.sh"
    [[ -f "$OB_DST/env.ini" ]] || cp "$OB_SRC/env.ini" "$OB_DST/"
    AA_SRC="$PRESETS_DIR/hooks/auto-approve"; AA_DST="$HOME/.claude/hooks/auto-approve"
    mkdir -p "$AA_DST/lib" "$AA_DST/modes"
    cp "$AA_SRC/auto-approve.sh" "$AA_DST/"
    cp "$AA_SRC/lib/"*.sh "$AA_SRC/lib/"*.py "$AA_DST/lib/"
    cp "$AA_SRC/modes/"*.sh "$AA_DST/modes/"
    cp "$AA_SRC/CREDITS.md" "$AA_DST/"
    chmod +x "$AA_DST/auto-approve.sh" "$AA_DST/modes/"*.sh
    [[ -f "$AA_DST/env.ini" ]]    || cp "$AA_SRC/env.ini" "$AA_DST/"
    [[ -f "$AA_DST/config.json" ]] || cp "$AA_SRC/config.json" "$AA_DST/"
    MM_SRC="$PRESETS_DIR/hooks/memory"; MM_DST="$HOME/.claude/hooks/memory"
    mkdir -p "$MM_DST/lib" "$MM_DST/modes"
    cp "$MM_SRC/memory.sh" "$MM_DST/"
    cp "$MM_SRC/lib/"*.sh "$MM_DST/lib/"
    cp "$MM_SRC/modes/"*.sh "$MM_DST/modes/"
    cp "$MM_SRC/CREDITS.md" "$MM_DST/"
    chmod +x "$MM_DST/memory.sh" "$MM_DST/modes/"*.sh
    [[ -f "$MM_DST/env.ini" ]]    || cp "$MM_SRC/env.ini" "$MM_DST/"
    [[ -f "$MM_DST/config.json" ]] || cp "$MM_SRC/config.json" "$MM_DST/"
    AR_SRC="$PRESETS_DIR/hooks/agent-router"; AR_DST="$HOME/.claude/hooks/agent-router"
    mkdir -p "$AR_DST"
    cp "$AR_SRC/router.py" "$AR_SRC/session-policy.py" "$AR_SRC/_lib.py" "$AR_DST/"
    cp "$AR_SRC/config.json" "$AR_SRC/README.md" "$AR_DST/"
    chmod +x "$AR_DST/router.py" "$AR_DST/session-policy.py"
    [[ -f "$AR_DST/env.ini" ]] || cp "$AR_SRC/env.ini" "$AR_DST/"
    RR_SRC="$PRESETS_DIR/hooks/run-report"; RR_DST="$HOME/.claude/hooks/run-report"
    mkdir -p "$RR_DST"
    cp "$RR_SRC/run-report.py" "$RR_SRC/_lib.py" "$RR_SRC/_usage.py" "$RR_SRC/README.md" "$RR_DST/"
    chmod +x "$RR_DST/run-report.py"
    [[ -f "$RR_DST/env.ini" ]] || cp "$RR_SRC/env.ini" "$RR_DST/"
    PG_SRC="$PRESETS_DIR/hooks/pack-guard"; PG_DST="$HOME/.claude/hooks/pack-guard"
    mkdir -p "$PG_DST"
    cp "$PG_SRC/pack-guard.py" "$PG_SRC/README.md" "$PG_DST/"
    chmod +x "$PG_DST/pack-guard.py"
    [[ -f "$PG_DST/env.ini" ]] || cp "$PG_SRC/env.ini" "$PG_DST/"
    PL_SRC="$PRESETS_DIR/hooks/plan-guard"; PL_DST="$HOME/.claude/hooks/plan-guard"
    mkdir -p "$PL_DST"
    cp "$PL_SRC/plan-guard.py" "$PL_SRC/README.md" "$PL_DST/"
    chmod +x "$PL_DST/plan-guard.py"
    [[ -f "$PL_DST/env.ini" ]] || cp "$PL_SRC/env.ini" "$PL_DST/"
    PX_SRC="$PRESETS_DIR/hooks/plan-regen"; PX_DST="$HOME/.claude/hooks/plan-regen"
    mkdir -p "$PX_DST"
    cp "$PX_SRC/plan-regen.py" "$PX_SRC/README.md" "$PX_DST/"
    chmod +x "$PX_DST/plan-regen.py"
    [[ -f "$PX_DST/env.ini" ]] || cp "$PX_SRC/env.ini" "$PX_DST/"
    CG_SRC="$PRESETS_DIR/hooks/changelog-gate"; CG_DST="$HOME/.claude/hooks/changelog-gate"
    mkdir -p "$CG_DST"
    cp "$CG_SRC/changelog-gate.py" "$CG_SRC/README.md" "$CG_DST/"
    chmod +x "$CG_DST/changelog-gate.py"
    [[ -f "$CG_DST/env.ini" ]] || cp "$CG_SRC/env.ini" "$CG_DST/"
    OS_SRC="$PRESETS_DIR/output-styles"; OS_DST="$HOME/.claude/output-styles"
    if [[ -d "$OS_SRC" ]]; then mkdir -p "$OS_DST"; cp "$OS_SRC/"*.md "$OS_DST/"; fi
    echo "Installed globally: log-bash-command + notify (active) + files auto-approve/ + memory/ + agent-router/ + run-report/ + pack-guard/ + plan-guard/ + plan-regen/ + changelog-gate/ + output-styles/ + statusline/ (NOT active)."
    echo "auto-approve, memory, agent-router, run-report, pack-guard, plan-guard, plan-regen, changelog-gate, output-style and statusline are included BY PROJECT / on call (see README)."
  else
    echo "--- dry-run: --global (hook files are not written) ---"
    RG_DST_CFG="$HOME/.claude/hooks/review-gate/config.json"
    if [[ ! -f "$RG_DST_CFG" ]]; then
      echo "review-gate: config.json is missing - a new template will be installed (checks: generated-assets, plan-check, tests-touched)"
    else
      RG_DST_SHA256="$(sha256sum "$RG_DST_CFG" | cut -d' ' -f1)"
      if [[ "$RG_DST_SHA256" == "$RG_OLD_STUB_SHA256" ]]; then
        echo "review-gate: config.json — old stub → will be migrated to the new template"
      else
        echo "review-gate: config.json — is not a stub (local selection) → will NOT be touched"
      fi
    fi
  fi
fi

[[ -n "$TARGET" ]] || { echo "Error: --target required" >&2; usage 1; }
[[ -d "$TARGET" ]] || { echo "Error: directory not found: $TARGET" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"

detect_presets() {
  local detected="yolo,base"
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

[[ -n "$PRESETS" ]] || { PRESETS="$(detect_presets)"; echo "Autodetect: $PRESETS"; }

PRESET_FILES=()
IFS=',' read -ra NAMES <<< "$PRESETS"
for name in "${NAMES[@]}"; do
  f="$PRESETS_DIR/settings.${name}.json"
  [[ -f "$f" ]] || { echo "Error: preset not found: $name ($f)" >&2; exit 1; }
  PRESET_FILES+=("$f")
done

DEST_DIR="$TARGET/.claude"
DEST="$DEST_DIR/$SETTINGS_FILE"

MERGED="$(python3 - "$DEST" "${PRESET_FILES[@]}" <<'PY'
import json, os, sys

dest_path, preset_paths = sys.argv[1], sys.argv[2:]

def load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        sys.stderr.write(f"ERROR: failed to read JSON {path}: {e}\n")
        sys.exit(1)

result = load(dest_path)
perms = result.setdefault("permissions", {})

for path in preset_paths:
    data = load(path)
    preset = data.get("permissions", {})
    for key in ("allow", "ask", "deny"):
        merged = perms.get(key, []) + [r for r in preset.get(key, [])
                                       if r not in perms.get(key, [])]
        if merged:
            perms[key] = merged
    if "defaultMode" in preset and "defaultMode" not in perms:
        perms["defaultMode"] = preset["defaultMode"]
    for event, entries in data.get("hooks", {}).items():
        existing = result.setdefault("hooks", {}).setdefault(event, [])
        existing.extend(e for e in entries if e not in existing)
    incoming_mcp = data.get("enabledMcpjsonServers", [])
    if incoming_mcp:
        cur_mcp = result.setdefault("enabledMcpjsonServers", [])
        cur_mcp.extend(s for s in incoming_mcp if s not in cur_mcp)

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
printf '%s\n' "$MERGED" > "$DEST.tmp" && mv -f "$DEST.tmp" "$DEST"
echo "Recorded: $DEST (presets: $PRESETS)"
if [[ -f "$DEST.bak" ]]; then echo "Backup:    $DEST.bak"; fi
