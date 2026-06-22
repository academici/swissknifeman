#!/usr/bin/env bash
# Режим file — один общий store на brain. Источается memory.sh.

mode_remember() { # brain type text
  local store; store="$(brain_store "$1")"
  [ -n "$store" ] || MEM_die "у brain '$1' не задан store"
  local f; f="$(store_remember "$store" "$2" "$1" "${CLAUDE_PROJECT_DIR:-$PWD}" "$3")" \
    || MEM_die "не удалось записать в $store"
  echo "memory(file): записано → $f"
}

mode_recall() { # brain query
  local store; store="$(brain_store "$1")"
  recall_print "$2" 5 "$store"
}

mode_members() { brain_members "$1"; }

mode_status() {
  local store; store="$(brain_store "$1")"
  echo "brain=$1 mode=file store=$store факты=$(store_count "$store") участники=$(brain_members "$1" | paste -sd, -)"
}

mode_sync() { echo "memory(file): sync не требуется (один store)"; }
