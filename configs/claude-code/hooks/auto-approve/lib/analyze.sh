#!/usr/bin/env bash
# Ядро анализа Bash-команд. Источать после common.sh. Конструкции — из config.json,
# здесь только логика. Требует глобал HOOK_DIR (каталог хука).

# prepare_bash: вытаскивает команду и грузит конфиг. 1 если нечего анализировать.
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

# load_config_vars <config-path>: читает конфиг в глобальные переменные/массивы.
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

# _normalize <cmd>: вырезаем кавычки (тела инлайн-скриптов не анализируем) и
# безопасные редиректы stderr/stdout, чтобы не путать с записью в файл.
_normalize() {
  printf '%s' "$1" \
    | sed -E "s/'[^']*'/ /g; s/\"[^\"]*\"/ /g" \
    | sed -E 's/[12]?>&[12]//g; s/&>[[:space:]]*\/dev\/null//g; s/[012]?>[[:space:]]*\/dev\/null//g'
}

# _match_any <text> <pattern...>: 0 если хоть один ERE-паттерн совпал.
_match_any() {
  local text="$1"; shift
  local re
  for re in "$@"; do
    [ -n "$re" ] || continue
    printf '%s' "$text" | grep -Eq "$re" && return 0
  done
  return 1
}

# _segments <scan>: режем на сегменты по разделителям/подстановкам.
_segments() {
  printf '%s' "$1" | sed -E \
    -e 's/\$\(/\n/g' -e 's/`/\n/g' -e 's/&&/\n/g' -e 's/\|\|/\n/g' -e 's/[|;(){}<>&]/\n/g'
}

# _segment_ok <segment>: 0 если безопасен/нейтрален, 1 если неизвестная голова.
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

# _shfmt_heads <cmd>: головы команд через AST shfmt (пусто при любой ошибке).
# Union-усиление: может только ДОБАВить проверок, не ослабить.
_shfmt_heads() {
  command -v shfmt >/dev/null 2>&1 || return 0
  local js
  js="$(printf '%s' "$1" | shfmt --tojson 2>/dev/null)"
  [ -n "$js" ] || js="$(printf '%s' "$1" | shfmt -tojson 2>/dev/null)"
  printf '%s' "$js" | jq -e . >/dev/null 2>&1 || return 0
  printf '%s' "$js" | jq -r \
    '[.. | objects | select(.Type=="CallExpr") | .Args[0].Parts[0].Value? // empty] | .[]' 2>/dev/null
}

# run_bash_analysis <strict|permissive|bypass>: полный флоу, завершает процесс.
# Использует HOOK_CMD. Денилисты — для всех режимов.
run_bash_analysis() {
  local mode="$1"
  local scan; scan="$(_normalize "$HOOK_CMD")"

  # 1) deny_hard => активный DENY (катастрофично) — во всех режимах.
  _match_any "$scan" "${DENY_HARD[@]}" \
    && emit_deny "Заблокировано: опасная операция (deny_hard). Выполните вручную при необходимости."

  # bypass: одобряем всё, что не катастрофично.
  if [ "$mode" = "bypass" ]; then
    emit_allow "bypass: одобрено всё, кроме deny_hard"
  fi

  # 2) deny_block_approve => fall-through на обычный промпт (мутация).
  _match_any "$scan" "${DENY_BLOCK[@]}" \
    && fallthrough_logged "мутация (deny_block_approve) — обычный промпт"

  # permissive: всё, что не запрещено выше, — одобряем.
  if [ "$mode" = "permissive" ]; then
    emit_allow "permissive: не совпало ни одно правило денилиста"
  fi

  # strict: каждая голова должна быть из безопасного набора.
  set -f
  local seg
  while IFS= read -r seg || [ -n "$seg" ]; do
    _segment_ok "$seg" || fallthrough_logged "strict: неизвестная голова команды"
  done < <(_segments "$scan")

  if [ "$USE_SHFMT" = "true" ]; then
    local h
    while IFS= read -r h || [ -n "$h" ]; do
      [ -n "$h" ] || continue
      case "$h" in git|gh|docker) continue;; esac
      case "$ALLOW_SET" in *" $h "*) continue;; esac
      fallthrough_logged "strict/shfmt: неизвестная голова '$h'"
    done < <(_shfmt_heads "$HOOK_CMD")
  fi
  set +f

  emit_allow "strict: все сегменты из безопасного набора (read-only)"
}
