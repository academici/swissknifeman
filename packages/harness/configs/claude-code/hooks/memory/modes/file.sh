#!/usr/bin/env bash

mode_remember() { # brain type text
  local store; store="$(brain_store "$1")"
  [ -n "$store" ] || MEM_die "y brain '$1' not specified store"
  local f; f="$(store_remember "$store" "$2" "$1" "${CLAUDE_PROJECT_DIR:-$PWD}" "$3")" \
    || MEM_die "could not be written to $store"
  echo "memory(file): recorded → $f"
}

mode_recall() { # brain query
  local store; store="$(brain_store "$1")"
  recall_print "$2" 5 "$store"
}

mode_members() { brain_members "$1"; }

mode_status() {
  local store; store="$(brain_store "$1")"
  echo "brain=$1 mode=file store=$store facts=$(store_count "$store") members=$(brain_members "$1" | paste -sd, -)"
}

mode_sync() { echo "memory(file): sync not required (one store)"; }
