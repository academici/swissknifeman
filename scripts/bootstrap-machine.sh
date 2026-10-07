#!/usr/bin/env bash
# bootstrap-machine.sh — idempotent machine-bootstrap umbrella (dotfiles-pattern,
# RAG:✅ 2026-07-12).
#
# Thin orchestrator: logic in packages (install.sh / harness / maind), script only
# calls them CLI in the correct order and checks rc (single source of truth - frame
# repo, double logic install/harness/maind here = defect). Restarting is safe:
# each stage uses merge-only/enable-idempotent package mechanisms.
#
# Steps:
#   1) install.sh          — CLI packages (skiller/harness/maind/analyst) + symlink swissknifeman
#   2) harness hooks --global        — hook files in ~/.claude/hooks (once per machine)
#   3) harness permissions --global  — global preset permissions (merge-only)
#   4) MCP-presets - y harness/maind now NO --global mechanism (mcp — per-project
#                              .mcp.json via --target); stage - information soft-skip,
#                              so as not to invent your own mechanism to bypass the single source of truth
#   5) maind service install — memory daemon as systemd --user (mild degradation without systemd)
#   6) swissknifeman doctor  — final diagnostics of all packages
#   7) projects manifest - clone missing + `swissknifeman setup <path>` (--projects FILE)
#
# Usage:
#   scripts/bootstrap-machine.sh [--dry-run] [--skip-projects] [--projects FILE] [--bin-dir DIR]
#   --dry-run        prints the stage plan, does not execute anything and does not write to disk
#   --skip-projects  skip step 7 (projects manifest) entirely, even if --projects set
#   --projects FILE  per-user projects manifest (JSON, scheme - docs/machine-manifest.example.json):
#                     clones missing repos and calls `swissknifeman setup <path>` by
#                     list; already cloned paths are NOT touched (pull does not - does not spoil someone else's
#                     operating status), only repeats onboard-check (idempotent)
#   --bin-dir DIR    where to put symlinks CLI (default ~/.local/bin, is forwarded to install.sh)
set -euo pipefail
# --- swissknifeman dev-clone guard (PLAN3 D13; removed at cutover) ---
_skm_guard_dir="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
while [ "$_skm_guard_dir" != "/" ] && [ ! -e "$_skm_guard_dir/.swissknifeman-dev" ]; do _skm_guard_dir="$(dirname "$_skm_guard_dir")"; done
if [ -e "$_skm_guard_dir/.swissknifeman-dev" ] && [ "${SKM_DEV_ALLOW_LIVE:-}" != "1" ]; then
  _skm_real_home="$(python3 -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)' 2>/dev/null || true)"
  if [ -z "$_skm_real_home" ] || [ "$(readlink -f "${HOME:-/}")" = "$(readlink -f "$_skm_real_home")" ]; then
    echo "SKM_DEV_GUARD: $_skm_guard_dir is a development clone; run inside scripts/dev-sandbox.sh or set SKM_DEV_ALLOW_LIVE=1" >&2
    exit 3
  fi
fi
unset _skm_guard_dir _skm_real_home
# --- end dev-clone guard ---

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$HOME/.local/bin"
DRY_RUN=false
SKIP_PROJECTS=false
PROJECTS_MANIFEST=""

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,28p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --skip-projects) SKIP_PROJECTS=true; shift ;;
    --projects) PROJECTS_MANIFEST="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

HARNESS="$REPO_ROOT/packages/harness/bin/harness"
MAIND="$REPO_ROOT/packages/maind/bin/maind"
SWISSKNIFEMAN="$REPO_ROOT/bin/swissknifeman"

STATUS=0  # only «hard» crashes (install.sh) raise the final rc; rest - WARN+skip

step() { echo; echo "== $* =="; }

# 1) install.sh packages + symlink swissknifeman — the only stage whose failure
#    is considered hard (without CLI packages further steps are meaningless).
step "1/7 install.sh (packages + symlink swissknifeman)"
if $DRY_RUN; then
  echo "+ $REPO_ROOT/install.sh --bin-dir $BIN_DIR"
else
  if ! "$REPO_ROOT/install.sh" --bin-dir "$BIN_DIR"; then
    echo "ERROR: install.sh ended with an error - see log above" >&2
    STATUS=1
  fi
fi

# 2) harness hooks --global — hook files in ~/.claude/hooks (merge-only, once per machine)
step "2/7 harness hooks --global"
if [[ -x "$HARNESS" ]]; then
  hargs=(hooks --global); $DRY_RUN && hargs+=(--dry-run)
  "$HARNESS" "${hargs[@]}" || echo "WARN: harness hooks --global failed - check manually" >&2
else
  echo "WARN: harness not found ($HARNESS) — skipping step (reinstall ./install.sh)" >&2
fi

# 3) harness permissions --global — global preset permissions (merge-only)
step "3/7 harness permissions --global"
if [[ -x "$HARNESS" ]]; then
  pargs=(permissions --global); $DRY_RUN && pargs+=(--dry-run)
  "$HARNESS" "${pargs[@]}" || echo "WARN: harness permissions --global failed - check manually" >&2
else
  echo "WARN: harness not found ($HARNESS) — skipping step" >&2
fi

# 4) global MCP-presets - y harness/maind there is currently no separate --global for mcp
#    (harness mcp — only per-project --target .mcp.json); we do nothing so as not to
#    invent their own mechanism to bypass the single source of truth of packages.
step "4/7 MCP-presets"
echo "SKIP: there is no global mechanism - MCP rolls out per-project (harness mcp --target / maind deploy)"

# 5) demon mAInd (systemd --user) — role-conscious: on role=client local daemon NOT
#    is set (second writer, ADR-0001), the client only reaches the host by memory.url.
#    Mild degradation if systemd/user-session unavailable (role standalone/host).
step "5/7 demon mAInd (maind service install)"
if [[ -x "$MAIND" ]]; then
  MEMORY_ROLE="$(PYTHONPATH="$REPO_ROOT/packages/maind/lib:$REPO_ROOT" python3 -c "
from maind.common import Env
from maind.config import Config
from maind.memory import memory_role
print(memory_role(Config.load(Env('$REPO_ROOT', 'bootstrap'))))
" 2>/dev/null || echo standalone)"
  if [[ "$MEMORY_ROLE" == "client" ]]; then
    echo "SKIP: memory.role=client — local daemon is NOT installed (second writer, ADR-0001);" \
         "client reaches the host via memory.url (see config.json), gate — maind health --strict"
  elif $DRY_RUN; then
    echo "+ $MAIND service install"
  else
    "$MAIND" service install || echo "WARN: maind service install not available (no systemd/user-sessions?) — raise manually: maind start --only memory" >&2
  fi
else
  echo "WARN: maind not found ($MAIND) — skipping step" >&2
fi

# 6) final diagnostics
step "6/7 swissknifeman doctor"
if $DRY_RUN; then
  echo "+ $SWISSKNIFEMAN doctor"
else
  if [[ -x "$SWISSKNIFEMAN" ]]; then
    "$SWISSKNIFEMAN" doctor || echo "WARN: doctor returned warnings/errors - see output above" >&2
  else
    echo "WARN: $SWISSKNIFEMAN not found - install.sh did not install a symlink" >&2
  fi
fi

# 7) projects manifest - per-user list of dependent repo (docs/machine-manifest.example.json):
#    clones missing ones, for already cloned ones pull DOES NOT (don't touch someone else's work
#    status) — only repeats `swissknifeman setup <path>` (onboard-check, idempotent).
step_projects() {
  local manifest="$1"
  if [[ ! -f "$manifest" ]]; then
    echo "ERROR: manifest not found: $manifest" >&2
    STATUS=1
    return
  fi
  local rows
  if ! rows="$(python3 - "$manifest" <<'PY'
import json, sys

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except (OSError, ValueError) as exc:
    print(f"invalid JSON manifest: {exc}", file=sys.stderr)
    sys.exit(1)

ok = True
for p in data.get("projects", []):
    repo = (p.get("repo") or "").strip()
    dest = (p.get("path") or "").strip()
    if not repo or not dest:
        print(f"record without required fields repo/path: {p}", file=sys.stderr)
        ok = False
        continue
    print(f"{repo}\x1f{dest}")
sys.exit(0 if ok else 1)
PY
  )"; then
    echo "ERROR: manifest is invalid: $manifest (see output above)" >&2
    STATUS=1
    return
  fi
  while IFS=$'\x1f' read -r repo dest; do
    [[ -z "$repo" ]] && continue
    dest_expanded="${dest/#\~/$HOME}"
    if $DRY_RUN; then
      if [[ -d "$dest_expanded/.git" ]]; then
        echo "+ (already cloned, skip clone) $SWISSKNIFEMAN setup $dest_expanded"
      else
        echo "+ git clone $repo $dest_expanded"
        echo "+ $SWISSKNIFEMAN setup $dest_expanded"
      fi
      continue
    fi
    if [[ -d "$dest_expanded/.git" ]]; then
      echo "SKIP clone (has already been cloned, pull we don't): $dest_expanded"
    else
      mkdir -p "$(dirname "$dest_expanded")"
      if git clone "$repo" "$dest_expanded"; then
        echo "OK clone: $repo -> $dest_expanded"
      else
        echo "WARN: git clone failed: $repo -> $dest_expanded — pass onboard for this project" >&2
        continue
      fi
    fi
    if [[ -x "$SWISSKNIFEMAN" ]]; then
      "$SWISSKNIFEMAN" setup "$dest_expanded" || echo "WARN: swissknifeman setup failed for $dest_expanded — check manually" >&2
    else
      echo "WARN: $SWISSKNIFEMAN not found - skip onboard for $dest_expanded" >&2
    fi
  done <<< "$rows"
}

step "7/7 projects manifest (--projects)"
if $SKIP_PROJECTS; then
  echo "NOTE: --skip-projects accepted - step skipped (manifest: ${PROJECTS_MANIFEST:-no})"
elif [[ -z "$PROJECTS_MANIFEST" ]]; then
  echo "NOTE: --projects not specified - step skipped (example manifest: docs/machine-manifest.example.json)"
else
  step_projects "$PROJECTS_MANIFEST"
fi

echo
if (( STATUS == 0 )); then
  echo "bootstrap-machine: ready (see WARN higher in optional steps)."
else
  echo "bootstrap-machine: completed with errors in required steps (see ERROR above)." >&2
fi
exit "$STATUS"
