#!/usr/bin/env bash
set -uo pipefail

changed="$( { git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -v '^$')"
[ -n "$changed" ] || exit 0

violations=0
while IFS= read -r f; do
  [ -f "$f" ] || continue
  line="$(grep -nE '^(<!-- |# |// )swissknifeman:generated[[:space:]]*$' "$f" 2>/dev/null | head -1 | cut -d: -f1)"
  if [ -n "$line" ]; then
    echo "$f:$line: файл сгенерирован паком (swissknifeman:generated) — правку перенести в override-файл (см. Extension-points в заголовке), не редактировать напрямую"
    violations=1
  fi
done <<< "$changed"

exit "$violations"
