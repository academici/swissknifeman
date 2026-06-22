#!/usr/bin/env bash
# Режим federation — истина = свои memory/ участников + общий store. recall
# читает по всем, ранжирует по совпадениям. remember пишет в общий store.
# Источается memory.sh.

# Каталоги памяти участника: <member>/.claude/memory + нативная память Claude
# Code (~/.claude/projects/<slug>/memory, slug = путь со слэшами → дефисами).
_member_dirs() {
  local p slug
  p="$(resolve_member_path "$1")"; [ -n "$p" ] || return
  [ -d "$p/.claude/memory" ] && echo "$p/.claude/memory"
  slug="$(printf '%s' "$p" | sed 's#/#-#g')"
  [ -d "$HOME/.claude/projects/$slug/memory" ] && echo "$HOME/.claude/projects/$slug/memory"
}

# Все каталоги brain: общий store + каталоги всех участников.
_all_dirs() {
  local b="$1" store m
  store="$(brain_store "$b")"; [ -n "$store" ] && [ -d "$store" ] && echo "$store"
  while IFS= read -r m; do [ -n "$m" ] && _member_dirs "$m"; done < <(brain_members "$b")
}

mode_remember() { # brain type text → в общий store (свои каталоги участников — их источник истины)
  local store; store="$(brain_store "$1")"
  [ -n "$store" ] || MEM_die "у brain '$1' не задан store"
  local f; f="$(store_remember "$store" "$2" "$1" "${CLAUDE_PROJECT_DIR:-$PWD}" "$3")" \
    || MEM_die "не удалось записать в $store"
  echo "memory(federation): записано в общий store → $f"
}

mode_recall() { # brain query
  local dirs; mapfile -t dirs < <(_all_dirs "$1")
  [ "${#dirs[@]}" -gt 0 ] || { echo "(нет доступных каталогов памяти у brain '$1')"; return; }
  recall_print "$2" 8 "${dirs[@]}"
}

mode_members() { brain_members "$1"; }

mode_status() {
  local dirs total=0 d c
  mapfile -t dirs < <(_all_dirs "$1")
  for d in "${dirs[@]}"; do c="$(store_count "$d")"; total=$((total + c)); done
  echo "brain=$1 mode=federation каталогов=${#dirs[@]} факты=$total участники=$(brain_members "$1" | paste -sd, -)"
}

mode_sync() { echo "memory(federation): индекс строится на лету при recall — sync не требуется"; }
