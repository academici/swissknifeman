#!/usr/bin/env bash
set -uo pipefail

changed="$( { git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -v '^$')"
[ -n "$changed" ] || exit 0

pkgs_lib="$(printf '%s\n' "$changed" | grep -oE '^packages/[^/]+/lib/' | sed -E 's#^packages/([^/]+)/lib/#\1#' | sort -u)"
[ -n "$pkgs_lib" ] || exit 0
pkgs_tests="$(printf '%s\n' "$changed" | grep -oE '^packages/[^/]+/tests/' | sed -E 's#^packages/([^/]+)/tests/#\1#' | sort -u)"

violations=0
while IFS= read -r pkg; do
  [ -n "$pkg" ] || continue
  if ! printf '%s\n' "$pkgs_tests" | grep -qx "$pkg"; then
    echo "packages/$pkg/lib/: changed without packages/$pkg/tests/ (possibly legal - refactor without changing behavior)"
    violations=1
  fi
done <<< "$pkgs_lib"

exit "$violations"
