#!/usr/bin/env bash
# check-env.sh — read-only check that this machine has what SwissKnifeMan needs.
#
# It installs and changes nothing: it looks for the programs and system features the modules call and prints, for every gap,
# the command that fixes it. Run it before `./install.sh`, and again after an OS upgrade.
#
# Usage:
#   scripts/check-env.sh [--strict] [--quiet] [--json] [--bin-dir DIR]
#   --strict   a missing "recommended" item is a failure too (exit 1), for CI and fresh-machine acceptance
#   --quiet    print only the items that are not ok
#   --json     print one JSON document (schema skm-env-check/v1) instead of the table
#   --bin-dir  where the commands are linked (default ~/.local/bin); must be on PATH
#
# Exit: 0 all required items present (and, with --strict, all recommended items); 1 something required is missing;
#       2 bad arguments.
#
# Levels: required    install.sh or the router cannot work without it
#         recommended a module degrades without it (named in the "needed for" column)
#         optional    only for a project stack or for development of this repository
set -uo pipefail

STRICT=false QUIET=false JSON=false BIN="${HOME}/.local/bin"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict) STRICT=true; shift ;;
    --quiet) QUIET=true; shift ;;
    --json) JSON=true; shift ;;
    --bin-dir) [[ $# -ge 2 ]] || { echo "ERROR: --bin-dir needs a value" >&2; exit 2; }; BIN="$2"; shift 2 ;;
    -h|--help) grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,18p'; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done

OS="$(uname -s)"
# One package manager decides the wording of every install hint.
PM=""
if   [[ "$OS" == Darwin ]] && command -v brew >/dev/null 2>&1; then PM=brew
elif command -v apt-get >/dev/null 2>&1; then PM=apt
elif command -v dnf >/dev/null 2>&1; then PM=dnf
elif command -v pacman >/dev/null 2>&1; then PM=pacman
fi

# pkg <apt-name> [brew-name] [dnf-name] [pacman-name] -> install command for the detected manager
pkg() {
  local apt="$1" brew="${2:-$1}" dnf="${3:-$1}" pacman="${4:-$1}"
  case "$PM" in
    apt) echo "sudo apt install $apt" ;;
    brew) echo "brew install $brew" ;;
    dnf) echo "sudo dnf install $dnf" ;;
    pacman) echo "sudo pacman -S $pacman" ;;
    *) echo "install '$apt' with your package manager" ;;
  esac
}

ROWS=()   # level|status|name|detail|needed-for|hint
add() { ROWS+=("$1|$2|$3|$4|$5|$6"); }

have() { command -v "$1" >/dev/null 2>&1; }

# version_ge <have> <want>: dotted numeric compare
version_ge() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]; }

# ---------------------------------------------------------------- required
if (( BASH_VERSINFO[0] >= 4 )) || [[ "$OS" == Darwin ]]; then
  add required ok bash "bash ${BASH_VERSION}" "install.sh, hooks" ""
else
  add required miss bash "bash ${BASH_VERSION} (< 4)" "install.sh, hooks" "$(pkg bash)"
fi

if have python3; then
  PYV="$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo 0)"
  if version_ge "$PYV" 3.11; then
    add required ok python3 "python3 $PYV" "every module" ""
  else
    add required miss python3 "python3 $PYV (needs >= 3.11)" "every module" "$(pkg python3)"
  fi
else
  add required miss python3 "not found" "every module" "$(pkg python3)"
fi

if have git; then
  add required ok git "$(git --version | sed 's/git version //')" "planner, delivery, project steps" ""
else
  add required miss git "not found" "planner, delivery, project steps" "$(pkg git)"
fi

for dir in "$HOME/.config" "$HOME/.local/state"; do
  probe="$dir"; while [[ ! -e "$probe" && "$probe" != / ]]; do probe="$(dirname "$probe")"; done
  if [[ -w "$probe" ]]; then
    add required ok "dir:${dir/#$HOME/~}" "writable (or creatable)" "machine config and state" ""
  else
    add required miss "dir:${dir/#$HOME/~}" "not writable" "machine config and state" "fix the owner/permissions of $probe"
  fi
done

# ------------------------------------------------------------- recommended
case ":${PATH}:" in
  *":${BIN}:"*) add recommended ok PATH "${BIN/#$HOME/~} is on PATH" "swissknifeman, skiller, maind, ... commands" "" ;;
  *) add recommended miss PATH "${BIN/#$HOME/~} is not on PATH" "swissknifeman, skiller, maind, ... commands" \
        "add to your shell profile: export PATH=\"$BIN:\$PATH\"  (or run install.sh --bin-dir DIR)" ;;
esac

if have jq; then
  add recommended ok jq "$(jq --version 2>/dev/null)" "Claude Code hooks, status line" ""
else
  add recommended miss jq "not found" "Claude Code hooks (review-gate, observer), status line" "$(pkg jq)"
fi

if have node; then
  NV="$(node --version 2>/dev/null | sed 's/^v//')"
  if version_ge "$NV" 18.0; then
    add recommended ok node "node $NV" "memory daemon (maind), docs build" ""
  else
    add recommended miss node "node $NV (needs >= 18)" "memory daemon (maind), docs build" "$(pkg nodejs node nodejs nodejs) (or use nvm)"
  fi
else
  add recommended miss node "not found" "memory daemon (maind), docs build" "$(pkg nodejs node nodejs nodejs) (or use nvm)"
fi

if have uvx; then
  add recommended ok uvx "$(uvx --version 2>/dev/null | head -1)" "code graph MCP (Serena)" ""
else
  add recommended miss uvx "not found" "code graph MCP (Serena) in project .mcp.json" \
      "install uv: curl -LsSf https://astral.sh/uv/install.sh | sh   (or: pipx install uv)"
fi

if [[ "$OS" == Linux ]]; then
  if have systemctl && systemctl --user show-environment >/dev/null 2>&1; then
    add recommended ok systemd-user "systemctl --user works" "maind service install (memory daemon)" ""
  else
    add recommended miss systemd-user "no systemd user session" "maind service install (memory daemon)" \
        "start the daemon by hand instead: maind start --only memory"
  fi

  # orch sandbox: bubblewrap + socat, then prove that user+net namespaces really start.
  BW=false SC=false
  have bwrap && BW=true
  have socat && SC=true
  if $BW; then add recommended ok bwrap "$(command -v bwrap)" "orch / Claude Code / Codex sandbox" ""
  else add recommended miss bwrap "not found" "orch / Claude Code / Codex sandbox" "$(pkg bubblewrap)"; fi
  if $SC; then add recommended ok socat "$(command -v socat)" "sandbox network proxy" ""
  else add recommended miss socat "not found" "sandbox network proxy" "$(pkg socat)"; fi
  if $BW; then
    if OUT="$(timeout 10 bwrap --ro-bind / / --unshare-user --unshare-net --dev /dev --proc /proc true 2>&1)"; then
      add recommended ok sandbox-namespaces "bwrap starts user+net namespaces" "orch / provider sandbox" ""
    else
      HINT="see 'Sandbox on Ubuntu 24.04+' in docs/getting-started.md"
      if [[ "$(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns 2>/dev/null)" == 1 ]]; then
        HINT="AppArmor restricts user namespaces: add a profile for bwrap (docs/getting-started.md, 'Sandbox on Ubuntu 24.04+')"
      fi
      add recommended miss sandbox-namespaces "bwrap cannot start: $(echo "$OUT" | head -1 | cut -c1-90)" "orch / provider sandbox" "$HINT"
    fi
  fi
else
  add recommended ok sandbox "$OS uses the system sandbox (Seatbelt); no bubblewrap needed" "orch / provider sandbox" ""
fi

# At least one agent client.
CLIENTS=()
for c in claude codex grok; do have "$c" && CLIENTS+=("$c"); done
if (( ${#CLIENTS[@]} )); then
  add recommended ok agent-client "found: ${CLIENTS[*]}" "the agent that reads skills and commands" ""
else
  add recommended miss agent-client "none of claude, codex, grok" "the agent that reads skills and commands" \
      "install at least one: Claude Code (https://claude.com/claude-code), Codex CLI or Grok CLI"
fi

# ---------------------------------------------------------------- optional
opt() {  # opt <bin> <needed-for> <hint>
  if have "$1"; then add optional ok "$1" "$(command -v "$1")" "$2" ""
  else add optional miss "$1" "not found" "$2" "$3"; fi
}
opt php "Laravel / PHP project packs, pint" "$(pkg php)"
opt composer "PHP projects" "$(pkg composer)"
opt pnpm "Node projects that use pnpm (husky, lint)" "corepack enable  (or: npm install -g pnpm)"
opt ruff "linting this repository (scripts/lint.sh)" "pipx install ruff   (or: pip install --user ruff)"
opt rsync "dev sandbox (scripts/dev-sandbox.sh)" "$(pkg rsync)"
opt pyright "type checking this repository (scripts/typecheck.sh)" "uv tool install pyright   (or: pipx install pyright, npm install -g pyright)"

# ------------------------------------------------------------------ report
REQ_FAIL=0 REC_FAIL=0
for r in "${ROWS[@]}"; do
  IFS='|' read -r level status _ <<<"$r"
  [[ "$status" == miss && "$level" == required ]] && REQ_FAIL=$((REQ_FAIL + 1))
  [[ "$status" == miss && "$level" == recommended ]] && REC_FAIL=$((REC_FAIL + 1))
done
RC=0
(( REQ_FAIL )) && RC=1
$STRICT && (( REC_FAIL )) && RC=1

if $JSON; then
  python3 - "$RC" "$REQ_FAIL" "$REC_FAIL" "${ROWS[@]}" <<'PY' 2>/dev/null || { echo '{"error":"python3 is required for --json"}'; }
import json, sys
rc, req, rec, *rows = sys.argv[1:]
items = []
for row in rows:
    level, status, name, detail, needed, hint = (row.split("|", 5) + [""] * 6)[:6]
    items.append({"level": level, "status": "ok" if status == "ok" else "missing", "name": name,
                  "detail": detail, "needed_for": needed, "fix": hint or None})
print(json.dumps({"schema": "skm-env-check/v1", "exit": int(rc), "required_missing": int(req),
                  "recommended_missing": int(rec), "items": items}, indent=2))
PY
  exit "$RC"
fi

if [[ -t 1 ]]; then G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' D=$'\e[2m' Z=$'\e[0m'; else G= Y= R= D= Z=; fi
CURRENT=""
for r in "${ROWS[@]}"; do
  IFS='|' read -r level status name detail needed hint <<<"$r"
  if [[ "$status" == ok ]]; then
    $QUIET && continue
    mark="${G}ok  ${Z}"
  elif [[ "$level" == required ]]; then mark="${R}FAIL${Z}"
  elif [[ "$level" == recommended ]]; then mark="${Y}warn${Z}"
  else mark="${D}skip${Z}"; fi
  if [[ "$level" != "$CURRENT" ]]; then CURRENT="$level"; printf '\n%s\n' "${level^^}"; fi
  printf '  %s  %-18s %s\n' "$mark" "$name" "$detail"
  if [[ "$status" != ok ]]; then
    [[ -n "$needed" ]] && printf '        %sneeded for:%s %s\n' "$D" "$Z" "$needed"
    [[ -n "$hint" ]] && printf '        %sfix:%s %s\n' "$D" "$Z" "$hint"
  fi
done

printf '\n'
if (( REQ_FAIL )); then
  printf '%s%d required item(s) missing: SwissKnifeMan cannot be installed yet.%s\n' "$R" "$REQ_FAIL" "$Z"
elif (( REC_FAIL )); then
  printf '%sRequired items present; %d recommended item(s) missing (modules named above run degraded).%s\n' "$Y" "$REC_FAIL" "$Z"
  $STRICT && printf '%s--strict: treated as failure.%s\n' "$R" "$Z"
else
  printf '%sEverything SwissKnifeMan needs is present.%s\n' "$G" "$Z"
fi
exit "$RC"
