#!/usr/bin/env bash

_member_dirs() {
  local p slug
  p="$(resolve_member_path "$1")"; [ -n "$p" ] || return
  [ -d "$p/.claude/memory" ] && echo "$p/.claude/memory"
  slug="$(printf '%s' "$p" | sed 's#/#-#g')"
  [ -d "$HOME/.claude/projects/$slug/memory" ] && echo "$HOME/.claude/projects/$slug/memory"
}

_all_dirs() {
  local b="$1" store m
  store="$(brain_store "$b")"; [ -n "$store" ] && [ -d "$store" ] && echo "$store"
  while IFS= read -r m; do [ -n "$m" ] && _member_dirs "$m"; done < <(brain_members "$b")
}

mode_remember() { # Store in the shared directory; member stores remain authoritative.
  local store; store="$(brain_store "$1")"
  [ -n "$store" ] || MEM_die "y brain '$1' not specified store"
  local f; f="$(store_remember "$store" "$2" "$1" "${CLAUDE_PROJECT_DIR:-$PWD}" "$3")" \
    || MEM_die "could not be written to $store"
  echo "memory(federation): written to general store → $f"
}

mode_recall() { # brain query
  local dirs; mapfile -t dirs < <(_all_dirs "$1")
  [ "${#dirs[@]}" -gt 0 ] || { echo "(no memory directories available brain '$1')"; return; }
  recall_print "$2" 8 "${dirs[@]}"
}

mode_members() { brain_members "$1"; }

mode_status() {
  local dirs total=0 d c
  mapfile -t dirs < <(_all_dirs "$1")
  for d in "${dirs[@]}"; do c="$(store_count "$d")"; total=$((total + c)); done
  echo "brain=$1 mode=federation directories=${#dirs[@]} facts=$total members=$(brain_members "$1" | paste -sd, -)"
}

mode_sync() { echo "memory(federation): index is built on the fly when recall — sync not required"; }
