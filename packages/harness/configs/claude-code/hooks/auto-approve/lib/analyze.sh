#!/usr/bin/env bash

# Heads that run the text of an argument as code: quoted bodies are scanned unmasked.
CARRIER_RE='(^|[^[:alnum:]_/.-])((ba|z|da|k|c)?sh|eval|exec|xargs|python[0-9.]*|node(js)?|deno|bun|perl|ruby|php|lua|env|nohup|timeout|nice|setsid|watch|su|runuser|script|parallel|ssh)([[:space:]]|$)'
# Variables that change what an allowed command does (command prefixes, export, declare, plain assignment).
UNSAFE_VAR_RE='^(PATH|IFS|HOME|SHELL|ENV|BASH_ENV|BASHOPTS|SHELLOPTS|PS[0-9]|PROMPT_COMMAND|GLOBIGNORE|CDPATH|FUNCNEST|LD_.*|DYLD_.*|GIT_.*|PAGER|EDITOR|VISUAL|LESS.*|PYTHON.*|NODE_.*|PERL.*|RUBY.*)$'
# The only variables a command prefix (VAR=x cmd) may set in strict mode.
SAFE_PREFIX_VAR_RE='^(LANG|LANGUAGE|LC_[A-Z_]+|TZ|NO_COLOR|CLICOLOR|FORCE_COLOR|COLUMNS|LINES|TERM|GIT_OPTIONAL_LOCKS|GIT_TERMINAL_PROMPT)$'

prepare_bash() {
  HOOK_CMD="$(hook_field '.tool_input.command')"
  [ -n "$HOOK_CMD" ] || return 1
  [ -f "$HOOK_DIR/config.json" ] || return 1
  local cfg_json
  cfg_json="$(jq -c . "$HOOK_DIR/config.json" 2>/dev/null)" || fallthrough
  local proj="${CLAUDE_PROJECT_DIR:-}"
  if [ -n "$proj" ] && [ -f "$proj/.claude/auto-approve.config.json" ]; then
    local pcfg
    pcfg="$(jq -c . "$proj/.claude/auto-approve.config.json" 2>/dev/null)" || fallthrough
    if allow_project_config "$HOOK_DIR"; then
      cfg_json="$pcfg"
    else
      cfg_json="$(merge_project_config "$cfg_json" "$pcfg")" || fallthrough
    fi
  fi
  load_config_vars "$cfg_json"
}

# A project file narrows the machine config: allow-lists intersect, deny-lists unite, and a
# switch can only be turned towards the safer side. The machine opts out via ALLOW_PROJECT_CONFIG=1.
merge_project_config() {
  jq -cn --argjson g "$1" --argjson p "$2" '
    def narrow(f): ($g | f) as $gv | ($p | f) as $pv
      | if $pv == null then $gv else [($gv // [])[] | select(. as $x | ($pv | index($x)) != null)] end;
    def unite(f): ((($g | f) // []) + (($p | f) // [])) | unique;
    $g
    | .trust_inline_interpreters = (($g.trust_inline_interpreters // false) and ($p.trust_inline_interpreters // true))
    | .use_shfmt_ast = (($g.use_shfmt_ast // false) or ($p.use_shfmt_ast // false))
    | .allow = narrow(.allow)
    | .inline_interpreters = narrow(.inline_interpreters)
    | .subcommand_read.git = narrow(.subcommand_read.git)
    | .subcommand_read.docker = narrow(.subcommand_read.docker)
    | .gh.read_verbs = narrow(.gh.read_verbs)
    | .gh.read_nouns_any = narrow(.gh.read_nouns_any)
    | .deny_hard = unite(.deny_hard)
    | .deny_block_approve = unite(.deny_block_approve)' 2>/dev/null
}

load_config_vars() {
  local cfg="$1"
  printf '%s' "$cfg" | jq -e . >/dev/null 2>&1 || fallthrough

  _cj() { printf '%s' "$cfg" | jq -r "$1"; }
  TRUST_INLINE="$(_cj '.trust_inline_interpreters // false')"
  USE_SHFMT="$(_cj '.use_shfmt_ast // false')"

  mapfile -t _ALLOW       < <(_cj '.allow[]?')
  mapfile -t _INLINE      < <(_cj '.inline_interpreters[]?')
  mapfile -t _GIT_READ    < <(_cj '.subcommand_read.git[]?')
  mapfile -t _DOCKER_READ < <(_cj '.subcommand_read.docker[]?')
  mapfile -t _GH_VERBS    < <(_cj '.gh.read_verbs[]?')
  mapfile -t _GH_NOUNS    < <(_cj '.gh.read_nouns_any[]?')
  mapfile -t DENY_HARD    < <(_cj '.deny_hard[]?')
  mapfile -t DENY_BLOCK   < <(_cj '.deny_block_approve[]?')

  ALLOW_SET=" ${_ALLOW[*]} "
  [ "$TRUST_INLINE" = "true" ] && ALLOW_SET="$ALLOW_SET${_INLINE[*]} "
  GIT_SET=" ${_GIT_READ[*]} "
  DOCKER_SET=" ${_DOCKER_READ[*]} "
  GH_VERB_SET=" ${_GH_VERBS[*]} "
  GH_NOUN_SET=" ${_GH_NOUNS[*]} "
}

# Drops stderr/stdout plumbing that is not a file write.
_strip_plumbing() {
  sed -E 's/[12]?>&[12]//g; s/&>[[:space:]]*\/dev\/null//g; s/[012]?>[[:space:]]*\/dev\/null//g'
}

# Sets HOOK_DYNAMIC (1: `$(`, backtick, `<(`, `>(` or `$'` outside single quotes) and HOOK_SCAN, the
# command with literal quoted text blanked and every code-carrying part kept.
scan_command() {
  local out=""
  if command -v python3 >/dev/null 2>&1; then
    out="$(printf '%s' "$1" | python3 "$HOOK_DIR/lib/shellscan.py" 2>/dev/null)" || out=""
  fi
  if [ -n "$out" ]; then
    HOOK_DYNAMIC="${out%%$'\n'*}"
    if [[ "$out" == *$'\n'* ]]; then HOOK_SCAN="${out#*$'\n'}"; else HOOK_SCAN=""; fi
    HOOK_SCAN="$(printf '%s' "$HOOK_SCAN" | _strip_plumbing)"
    return 0
  fi
  # No python3: coarse fallback, quoted text dropped, any substitution marker counts as dynamic.
  HOOK_DYNAMIC=0
  printf '%s' "$1" | grep -Eq '\$\(|`|<\(|>\(|\$'"'" && HOOK_DYNAMIC=1
  HOOK_SCAN="$(printf '%s' "$1" | sed -E "s/'[^']*'/ /g; s/\"[^\"]*\"/ /g" | _strip_plumbing)"
  [ "$2" != strict ]
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

_has_arg() {
  local re="$1" a; shift
  for a in "$@"; do [[ "$a" =~ $re ]] && return 0; done
  return 1
}

# Flags that turn an allowed read command into a writer or a launcher.
_args_ok() {
  local head="$1"; shift
  case "$head" in
    find)  _has_arg '^-(exec|execdir|ok|okdir|delete|fprint|fprint0|fprintf|fls)$' "$@" && return 1;;
    sort)  _has_arg '^(-[a-zA-Z0-9]*o|--output(=.*)?|--compress-program(=.*)?)$' "$@" && return 1;;
    tree)  _has_arg '^(-[a-zA-Z]*o|--output(=.*)?)$' "$@" && return 1;;
    yq)    _has_arg '^(-([is]|[a-zA-Z]?[is][a-zA-Z]?)|--inplace|--split-exp(=.*)?)$' "$@" && return 1;;
    xxd)   _has_arg '^(-[a-zA-Z]*r|-revert)$' "$@" && return 1;;
    file)  _has_arg '^(-[a-zA-Z]*C|--compile)$' "$@" && return 1;;
    date)  _has_arg '^(-s.*|--set(=.*)?)$' "$@" && return 1;;
    hostname) _has_arg '^[^-]' "$@" && return 1;;
    rg|ag) _has_arg '^--(pre|hostname-bin|pager)(=.*)?$' "$@" && return 1;;
    uniq)  local n=0 a; for a in "$@"; do [[ "$a" == -* ]] || n=$((n + 1)); done; [ "$n" -gt 1 ] && return 1;;
    env)   _has_arg '^[^-]|^-[^0]|^--[^n]' "$@" && return 1;;
  esac
  return 0
}

_git_branch_ok() {
  _has_arg '^(-[a-zA-Z]*[dDmMcCfutU]|--(delete|move|copy|force|set-upstream-to|set-upstream|unset-upstream|track|no-track|edit-description|create-reflog))' "$@" && return 1
  _has_arg '^(-[a-zA-Z]*l|--(list|contains|no-contains|merged|no-merged|points-at|show-current))' "$@" && return 0
  _has_arg '^[^-]' "$@" && return 1   # a bare name creates a branch
  return 0
}

_gh_api_ok() {
  local a prev=""
  for a in "$@"; do
    case "$a" in
      -f*|-F*|--field|--field=*|--raw-field|--raw-field=*|--input|--input=*) return 1;;
      -X?*) [[ "${a#-X}" =~ ^[Gg][Ee][Tt]$ ]] || return 1;;
      --method=*) [[ "${a#--method=}" =~ ^[Gg][Ee][Tt]$ ]] || return 1;;
    esac
    case "$prev" in
      -X|--method) [[ "$a" =~ ^[Gg][Ee][Tt]$ ]] || return 1;;
    esac
    prev="$a"
  done
  return 0
}

_assign_name_ok() {
  local name="${1%%=*}"
  ! [[ "$name" =~ $UNSAFE_VAR_RE ]]
}

_segment_ok() {
  local seg="$1"
  seg="${seg#"${seg%%[![:space:]]*}"}"; seg="${seg%"${seg##*[![:space:]]}"}"
  [ -z "$seg" ] && return 0

  local vname
  while [[ "$seg" =~ ^([A-Za-z_][A-Za-z0-9_]*)=[^[:space:]]*[[:space:]]+(.*)$ ]]; do
    vname="${BASH_REMATCH[1]}"; seg="${BASH_REMATCH[2]}"
    [[ "$vname" =~ $SAFE_PREFIX_VAR_RE ]] || return 1
  done
  if [[ "$seg" =~ ^([A-Za-z_][A-Za-z0-9_]*)=[^[:space:]]*$ ]]; then
    _assign_name_ok "${BASH_REMATCH[1]}"; return
  fi

  local -a w
  read -ra w <<< "$seg"
  while [ ${#w[@]} -gt 0 ]; do
    case "${w[0]}" in
      '!'|time|then|do|else|elif|in) w=("${w[@]:1}");;
      *) break;;
    esac
  done
  [ ${#w[@]} -eq 0 ] && return 0

  local head="${w[0]}" a
  case "$head" in
    export|declare|typeset|readonly|local)
      for a in "${w[@]:1}"; do
        [[ "$a" == *=* ]] && ! _assign_name_ok "$a" && return 1
      done
      return 0;;
    if|for|while|until|case|esac|fi|done|function|'{'|'}'|'['|'[['|']'|']]'|return|break|continue|exit|set|unset|read|shift|wait|true|false|:)
      return 0;;
    safe-rm|safe-rmdir)
      return 0;;   # Added only after a safe-dirs verdict (safedirs_mask).
  esac

  case "$head" in
    git)
      case "$GIT_SET" in *" ${w[1]:-} "*) ;; *) return 1;; esac
      _has_arg '^--(output|ext-diff|upload-pack|receive-pack|exec)(=.*)?$' "${w[@]:2}" && return 1
      case "${w[1]}" in
        branch) _git_branch_ok "${w[@]:2}" || return 1;;
        reflog) _has_arg '^(expire|delete)$' "${w[@]:2}" && return 1;;
      esac
      return 0;;
    docker) case "$DOCKER_SET" in *" ${w[1]:-} "*) return 0;; esac; return 1;;
    gh)
      case "$GH_NOUN_SET" in
        *" ${w[1]:-} "*)
          [ "${w[1]}" = api ] && { _gh_api_ok "${w[@]:2}" || return 1; }
          return 0;;
      esac
      case "$GH_VERB_SET" in *" ${w[2]:-} "*) return 0;; esac
      return 1;;
  esac

  case "$ALLOW_SET" in *" $head "*) _args_ok "$head" "${w[@]:1}"; return;; esac
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
  if ! scan_command "$HOOK_CMD" "$mode"; then
    fallthrough_logged "strict: python3 unavailable, quote-aware scan impossible"
  fi
  local scan="$HOOK_SCAN"
  local carrier=0
  printf '%s' "$scan" | grep -Eq "$CARRIER_RE" && carrier=1

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
  # A shell or interpreter runs its quoted argument as code: the lists see that text unmasked too.
  if [ "$carrier" = 1 ]; then
    _match_any "$HOOK_CMD" "${DENY_HARD[@]}" \
      && emit_deny "Blocked: dangerous operation in the code of a quoted argument (deny_hard). Perform manually if necessary."
  fi

  if [ "$mode" = "bypass" ]; then
    emit_allow "bypass: everything is approved except deny_hard"
  fi

  _match_any "$scan" "${DENY_BLOCK[@]}" \
    && fallthrough_logged "mutation (deny_block_approve) — regular prompt"
  if [ "$carrier" = 1 ]; then
    _match_any "$HOOK_CMD" "${DENY_BLOCK[@]}" \
      && fallthrough_logged "mutation inside a quoted argument (deny_block_approve) — regular prompt"
  fi

  if [ "$mode" = "permissive" ]; then
    emit_allow "permissive: did not match any denilista rules"
  fi

  # Strict without an AST parser must not trust the regex view of a command with substitutions.
  if [ "$HOOK_DYNAMIC" = 1 ] && ! command -v shfmt >/dev/null 2>&1; then
    fallthrough_logged "strict: command substitution and no shfmt to parse it (fail-closed)"
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
