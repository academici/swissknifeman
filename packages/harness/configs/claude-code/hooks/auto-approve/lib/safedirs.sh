#!/usr/bin/env bash

safedirs_applicable() {
  printf '%s' "$1" | grep -Eq '(^|[^[:alnum:]_/.-])(rm|rmdir)([[:space:]]|$)'
}

safedirs_verdict() {
  command -v python3 >/dev/null 2>&1 || return 1
  [ "$(printf '%s' "$HOOK_INPUT" | python3 "$HOOK_DIR/lib/safedirs.py" 2>/dev/null)" = "safe" ]
}

safedirs_mask() {
  printf '%s' "$1" | sed -E \
    -e 's/(^|[^[:alnum:]_/.-])rm([[:space:]]|$)/\1safe-rm\2/g' \
    -e 's/(^|[^[:alnum:]_/.-])rmdir([[:space:]]|$)/\1safe-rmdir\2/g'
}
