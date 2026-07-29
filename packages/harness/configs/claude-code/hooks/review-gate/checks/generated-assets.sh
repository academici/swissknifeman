#!/usr/bin/env bash
# generated-assets.sh — G1 (strict-класс, режим объявлен в config.json).
# Среди изменённых файлов ищет заголовок `swissknifeman:generated` (agent-packs
# provenance-блок, см. lib/harness/agentpacks.py provenance_header): найден →
# нарушение, правку переносить в override-файл (Extension-points из заголовка),
# не в сам сгенерированный файл. exit 0 = чисто, ≠0 = нарушение; stdout = file:line.
set -uo pipefail

changed="$( { git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -v '^$')"
[ -n "$changed" ] || exit 0

violations=0
while IFS= read -r f; do
  [ -f "$f" ] || continue
  # Якорь на РЕАЛЬНЫЙ формат заголовка (provenance_header): строка начинается
  # ИМЕННО с комментария + маркера, а не любое упоминание строки в прозе/тексте
  # теста (иначе ловит собственные докстринги/тесты review-gate — ложный
  # позитив, найден live-прогоном P9.1).
  line="$(grep -nE '^(<!-- |# |// )swissknifeman:generated[[:space:]]*$' "$f" 2>/dev/null | head -1 | cut -d: -f1)"
  if [ -n "$line" ]; then
    echo "$f:$line: файл сгенерирован паком (swissknifeman:generated) — правку перенести в override-файл (см. Extension-points в заголовке), не редактировать напрямую"
    violations=1
  fi
done <<< "$changed"

exit "$violations"
