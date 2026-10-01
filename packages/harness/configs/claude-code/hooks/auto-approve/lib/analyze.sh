#!/usr/bin/env bash

prepare_bash() {
  HOOK_CMD="$(hook_field '.tool_input.command')"
  [ -n "$HOOK_CMD" ] || return 1
  local cfg=""
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -f "$CLAUDE_PROJECT_DIR/.claude/auto-approve.config.json" ]; then
    cfg="$CLAUDE_PROJECT_DIR/.claude/auto-approve.config.json"
  elif [ -f "$HOOK_DIR/config.json" ]; then
    cfg="$HOOK_DIR/config.json"
  else
    return 1
  fi
  load_config_vars "$cfg"
}

load_config_vars() {
  local cfg="$1"
  jq -e . "$cfg" >/dev/null 2>&1 || fallthrough

  TRUST_INLINE="$(jq -r '.trust_inline_interpreters // false' "$cfg")"
  USE_SHFMT="$(jq -r '.use_shfmt_ast // false' "$cfg")"

  mapfile -t _ALLOW       < <(jq -r '.allow[]?' "$cfg")
  mapfile -t _INLINE      < <(jq -r '.inline_interpreters[]?' "$cfg")
  mapfile -t _GIT_READ    < <(jq -r '.subcommand_read.git[]?' "$cfg")
  mapfile -t _DOCKER_READ < <(jq -r '.subcommand_read.docker[]?' "$cfg")
  mapfile -t _GH_VERBS    < <(jq -r '.gh.read_verbs[]?' "$cfg")
  mapfile -t _GH_NOUNS    < <(jq -r '.gh.read_nouns_any[]?' "$cfg")
  mapfile -t DENY_HARD    < <(jq -r '.deny_hard[]?' "$cfg")
  mapfile -t DENY_BLOCK   < <(jq -r '.deny_block_approve[]?' "$cfg")

  ALLOW_SET=" ${_ALLOW[*]} "
  [ "$TRUST_INLINE" = "true" ] && ALLOW_SET="$ALLOW_SET${_INLINE[*]} "
  GIT_SET=" ${_GIT_READ[*]} "
  DOCKER_SET=" ${_DOCKER_READ[*]} "
  GH_VERB_SET=" ${_GH_VERBS[*]} "
  GH_NOUN_SET=" ${_GH_NOUNS[*]} "
}

_normalize() {
  printf '%s' "$1" \
    | sed -E "s/'[^']*'/ /g; s/\"[^\"]*\"/ /g" \
    | sed -E 's/[12]?>&[12]//g; s/&>[[:space:]]*\/dev\/null//g; s/[012]?>[[:space:]]*\/dev\/null//g'
}

_match_any() {
  local text="$1"; shift
  local re
  for re in "$@"; do
    [ -n "$re" ] || continue
    printf '%s' "$text" | grep -Eq "$re" && return 0
  done
  return 1
}

_segments() {
  printf '%s' "$1" | sed -E \
    -e 's/\$\(/\n/g' -e 's/`/\n/g' -e 's/&&/\n/g' -e 's/\|\|/\n/g' -e 's/[|;(){}<>&]/\n/g'
}

_segment_ok() {
  local seg="$1"
  seg="${seg#"${seg%%[![:space:]]*}"}"; seg="${seg%"${seg##*[![:space:]]}"}"
  [ -z "$seg" ] && return 0

  while [[ "$seg" =~ ^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+(.*)$ ]]; do
    seg="${BASH_REMATCH[1]}"
  done
  [[ "$seg" =~ ^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*$ ]] && return 0

  local -a w
  read -ra w <<< "$seg"
  while [ ${#w[@]} -gt 0 ]; do
    case "${w[0]}" in
      '!'|time|then|do|else|elif|in) w=("${w[@]:1}");;
      *) break;;
    esac
  done
  [ ${#w[@]} -eq 0 ] && return 0

  local head="${w[0]}"
  case "$head" in
    if|for|while|until|case|esac|fi|done|function|'{'|'}'|'['|'[['|']'|']]'|return|break|continue|exit|local|export|declare|typeset|readonly|set|unset|read|shift|wait|true|false|:)
      return 0;;
    safe-rm|safe-rmdir)
      return 0;;   # Added only after a safe-dirs verdict (safedirs_mask).
  esac

  case "$head" in
    git)    case "$GIT_SET"    in *" ${w[1]:-} "*) return 0;; esac; return 1;;
    docker) case "$DOCKER_SET" in *" ${w[1]:-} "*) return 0;; esac; return 1;;
    gh)
      case "$GH_NOUN_SET" in *" ${w[1]:-} "*) return 0;; esac
      case "$GH_VERB_SET" in *" ${w[2]:-} "*) return 0;; esac
      return 1;;
  esac

  case "$ALLOW_SET" in *" $head "*) return 0;; esac
  return 1
}

_shfmt_heads() {
  command -v shfmt >/dev/null 2>&1 || return 0
  local js
  js="$(printf '%s' "$1" | shfmt --tojson 2>/dev/null)"
  [ -n "$js" ] || js="$(printf '%s' "$1" | shfmt -tojson 2>/dev/null)"
  printf '%s' "$js" | jq -e . >/dev/null 2>&1 || return 0
  printf '%s' "$js" | jq -r \
    '[.. | objects | select(.Type=="CallExpr") | .Args[0].Parts[0].Value? // empty] | .[]' 2>/dev/null
}

run_bash_analysis() {
  local mode="$1"
  local scan; scan="$(_normalize "$HOOK_CMD")"

  local scan_dh; scan_dh="$(printf '%s' "$scan" \
    | sed -E 's/(^|[^[:alnum:]_/.-])git[[:space:]]+rm([[:space:]]|$)/\1git-rm\2/g')"

  local SAFEDIRS_OK=0
  if safedirs_applicable "$scan_dh" && safedirs_verdict; then
    SAFEDIRS_OK=1
    scan_dh="$(safedirs_mask "$scan_dh")"
    scan="$(safedirs_mask "$scan")"
  fi

  _match_any "$scan_dh" "${DENY_HARD[@]}" \
    && emit_deny "Blocked: dangerous operation (deny_hard). Perform manually if necessary. rm in trusted folders you can allow: harness safe-dirs (safe-dirs.json in the root of the repo swissknifeman)."

  if [ "$mode" = "bypass" ]; then
    emit_allow "bypass: everything is approved except deny_hard"
  fi

  _match_any "$scan" "${DENY_BLOCK[@]}" \
    && fallthrough_logged "mutation (deny_block_approve) — regular prompt"

  if [ "$mode" = "permissive" ]; then
    emit_allow "permissive: did not match any denilista rules"
  fi

  set -f
  local seg
  while IFS= read -r seg || [ -n "$seg" ]; do
    _segment_ok "$seg" || fallthrough_logged "strict: unknown team head"
  done < <(_segments "$scan")

  if [ "$USE_SHFMT" = "true" ]; then
    local h
    while IFS= read -r h || [ -n "$h" ]; do
      [ -n "$h" ] || continue
      case "$h" in git|gh|docker) continue;; esac
      case "$h" in rm|rmdir) [ "$SAFEDIRS_OK" = 1 ] && continue;; esac
      case "$ALLOW_SET" in *" $h "*) continue;; esac
      fallthrough_logged "strict/shfmt: unknown head '$h'"
    done < <(_shfmt_heads "$HOOK_CMD")
  fi
  set +f

  emit_allow "strict: all segments from the safe set (read-only)"
}
