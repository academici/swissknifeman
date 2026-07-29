#!/usr/bin/env bash
# plan-citations.sh — третья точка принуждения гейта цитат (P11.7); doctor
# показывает её сырым именем (нет короткого кода в `_REVIEW_GATE_CHECK_CODES`
# — fallback `doctor.py`, намеренно не тронутый этим item'ом). Режим — по
# факту чистоты после P11.5 (см. `config.json`). Изменения задели
# `plans/<ID>/` → прогон `plans/verify-citations.py plans/<ID>
# --strict` по КАЖДОМУ задетому плану; нарушением считаются ТОЛЬКО находки
# сверх baseline-перечня (`plans/verify-citations-known-exceptions.json`) —
# скрипт сам вычитает known exceptions, гейт лишь читает его exit-код/вывод.
# exit 0 = чисто, ≠0 = нарушение; stdout = plans/<ID>: <цитата> — <причина>.
set -uo pipefail

changed="$( { git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -v '^$')"
[ -n "$changed" ] || exit 0

# Требуем ХВОСТОВОЙ слэш: только реальные подкаталоги plans/<ID>/..., а не
# корневые файлы (plans/README.md, plans/ACTIVE.md) — тот же баг, найденный
# live-прогоном P9.1 на соседней проверке `plan-lint.sh`.
plan_ids="$(printf '%s\n' "$changed" | grep -oE '^plans/[^/]+/' | sed -E 's#^plans/##; s#/$##' | sort -u)"
[ -n "$plan_ids" ] || exit 0

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
vc_py="$repo_root/plans/verify-citations.py"
[ -f "$vc_py" ] || exit 0   # гейт цитат не завезён в это дерево — не наш случай

violations=0
while IFS= read -r pid; do
  [ -n "$pid" ] || continue
  [ -d "$repo_root/plans/$pid" ] || continue
  out="$(python3 "$vc_py" "$repo_root/plans/$pid" --strict 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    while IFS= read -r line; do
      case "$line" in
        *"→"*)
          after="${line#*→ }"
          echo "plans/$pid: ${after}"
          ;;
      esac
    done <<< "$out"
    violations=1
  fi
done <<< "$plan_ids"

exit "$violations"
