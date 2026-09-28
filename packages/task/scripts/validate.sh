#!/usr/bin/env bash
# validate.sh — структурные проверки пакета task (CI + локально), по образцу
# packages/maind/scripts/validate.sh. Проверяет: компиляцию Python (lib/tests/scripts),
# синтаксис bash (scripts/*.sh), обязательные файлы, frontmatter slash-команд
# (description/model/effort — task пинит модель/effort каждой командой), unittest,
# и — если в монорепо уже есть plans/ (plan-протокол) — прогон scripts/plan-lint.py
# по нему (отсутствие plans/ — не ошибка, пакет task её не создаёт).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
plan_targets=()
fleet=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan) [[ $# -ge 2 ]] || { echo "--plan требует путь" >&2; exit 2; }
      plan_targets+=("$(realpath "$2")"); shift 2 ;;
    --fleet) fleet=true; shift ;;
    -h|--help) echo "validate.sh [--plan PATH ...] [--fleet] — пакет; выбранные планы или CI/release fleet"; exit 0 ;;
    *) echo "Неизвестный параметр: $1" >&2; exit 2 ;;
  esac
done
cd "$REPO_ROOT"
fail=0
err() { echo "  FAIL: $*" >&2; fail=1; }

echo "[1/5] python compile"
python3 -m compileall -q lib tests scripts || err "py_compile"

echo "[2/5] bash syntax"
for f in scripts/*.sh; do
  bash -n "$f" || err "bash -n $f"
done

echo "[3/5] обязательные файлы"
for f in .claude-plugin/plugin.json lib/task/__init__.py lib/task/plan_lint.py \
         scripts/plan-lint.py commands/design.md; do
  [[ -e "$f" ]] || err "нет файла: $f"
done

echo "[4/5] slash-команды (frontmatter: description/model/effort)"
python3 - <<'PY' || err "битый frontmatter в commands/*.md"
import glob, sys

VALID_MODELS = {"opus", "sonnet", "haiku"}
VALID_EFFORTS = {"low", "medium", "high", "xhigh"}
bad = []
for f in sorted(glob.glob("commands/*.md")):
    lines = open(f, encoding="utf-8").read().replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        bad.append(f"{f}: нет открывающего ---")
        continue
    fm, closed = {}, False
    for ln in lines[1:]:
        if ln.strip() == "---":
            closed = True
            break
        if ":" in ln:
            k, v = ln.split(":", 1)
            fm[k.strip()] = v.strip().strip('"')
    if not closed:
        bad.append(f"{f}: frontmatter не закрыт")
        continue
    if not fm.get("description"):
        bad.append(f"{f}: пустой/нет description")
    # plan-run.md (D18) намеренно БЕЗ model/effort — наследует сессию, единственное исключение
    if f != "commands/plan-run.md":
        if fm.get("model") not in VALID_MODELS:
            bad.append(f"{f}: model «{fm.get('model')}» не из {sorted(VALID_MODELS)}")
        if fm.get("effort") not in VALID_EFFORTS:
            bad.append(f"{f}: effort «{fm.get('effort')}» не из {sorted(VALID_EFFORTS)}")
    elif fm.get("model") or fm.get("effort"):
        bad.append(f"{f}: model/effort ЗАПИНЕНЫ — plan-run обязана их не нести (D18)")
for b in bad:
    print("  FAIL:", b, file=sys.stderr)
sys.exit(1 if bad else 0)
PY

echo "[5/6] тесты + явно выбранный plan-lint"
# lib/ — пакет task; MONOREPO_ROOT (на два уровня выше пакета) — чтобы опционально
# импортировался core (fallback core.term.warn внутри plan_lint.py, см. его try/except).
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest discover -s tests -p "test_*.py" || err "unittest"

if $fleet && [[ -n "$MONOREPO_ROOT" && -d "$MONOREPO_ROOT/plans" ]]; then
  plan_targets+=("$MONOREPO_ROOT/plans")
fi
for plan_target in "${plan_targets[@]}"; do
  python3 scripts/plan-lint.py "$plan_target" || err "plan-lint.py $plan_target"
done
if [[ ${#plan_targets[@]} -eq 0 ]]; then
  echo "  plan regression не запрошен; --plan PATH для задачи, --fleet для CI/release"
fi

# --conflicts (2026.07.31-SKM-LEAN P5.9, roadmap plan-audit-loop.md §A.1) — дешёвая
# сверка «EN-only канон ↔ реализация» без плана на входе; отсутствие канона fail-closed.
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}" \
  python3 scripts/plan-lint.py --conflicts || err "plan-lint.py --conflicts — см. вывод выше"

# P0.7 — паритет провайдерских проекций команд держался только на unit-тестах; гейт
# генератора покрывает ещё и claude-golden, runtime-копию plan-protocol и publication-lock.

echo "[5b/6] publication version ↔ umbrella ↔ manifests"
if [[ -n "$MONOREPO_ROOT" ]]; then
  python3 "$REPO_ROOT/scripts/check-publication-version.py" "$MONOREPO_ROOT" \
    || err "publication version drift — bump plugin_version + render-provider-commands"
fi

echo "[6/6] проекции команд провайдеров (render-provider-commands --check)"
if [[ -n "$MONOREPO_ROOT" ]]; then
  python3 scripts/render-provider-commands.py --check --root "$MONOREPO_ROOT" \
    || err "проекции команд разошлись с каноном — python3 packages/task/scripts/render-provider-commands.py --write --root ."
else
  echo "  проекции команд: монорепо-корень не найден (standalone-раскладка) — гейт пропущен"
fi

echo ""
if [[ "$fail" -eq 0 ]]; then echo "validate: OK"; else echo "validate: ПРОВАЛ" >&2; exit 1; fi
