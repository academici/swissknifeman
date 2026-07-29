#!/usr/bin/env bash
# plan-lint.sh — G2 (strict-класс). Изменения задели `plans/<ID>/` → прогон
# `packages/task/scripts/plan-lint.py` по КАЖДОМУ задетому плану; ненулевой
# exit лаунчера (ERROR-гейт, default `--gate all`) → нарушение.
# exit 0 = чисто, ≠0 = нарушение; stdout = plans/<ID>: первая строка ERROR.
set -uo pipefail

changed="$( { git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -v '^$')"
[ -n "$changed" ] || exit 0

# Требуем ХВОСТОВОЙ слэш: только реальные подкаталоги plans/<ID>/..., а не
# корневые файлы (plans/README.md, plans/ACTIVE.md) — иначе `grep` без слэша
# принимал их за ID плана и plan-lint.py падал «путь не найден» (найдено
# live-прогоном P9.1).
plan_ids="$(printf '%s\n' "$changed" | grep -oE '^plans/[^/]+/' | sed -E 's#^plans/##; s#/$##' | sort -u)"
[ -n "$plan_ids" ] || exit 0

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
lint_py="$repo_root/packages/task/scripts/plan-lint.py"
[ -f "$lint_py" ] || exit 0   # плана-протокола нет в этом дереве — не наш случай

violations=0
while IFS= read -r pid; do
  [ -n "$pid" ] || continue
  out="$(python3 "$lint_py" "$repo_root/plans/$pid" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    first_error="$(printf '%s\n' "$out" | grep '^ERROR:' | head -1)"
    echo "plans/$pid: plan-lint ERROR — ${first_error:-см. полный вывод plan-lint.py}"
    violations=1
  fi
done <<< "$plan_ids"

exit "$violations"
