#!/usr/bin/env bash
# Прогон тестов пакета lib/swissknifeman (stdlib unittest, без зависимостей).
# Запуск: scripts/test.sh [-v]   (-v — подробный вывод unittest)
# Тесты гоняют CLI против синтетического реестра в tmpdir (tests/fixtures.py),
# настоящий реестр не трогается. Используется локально и из validate.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: тесты требуют python3" >&2
  exit 1
fi

# lib/ — пакет swissknifeman; REPO_ROOT — чтобы импортировался tests.fixtures.
export PYTHONPATH="$REPO_ROOT/lib:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

verbose=""
[[ "${1:-}" == "-v" ]] && verbose="-v"

# Тесты гоняют реальные CLI-команды, поэтому stdout/stderr забиты их штатными
# отчётами и ожидаемыми WARN/ERROR (проверяется поведение, не вывод). В обычном
# режиме копим весь вывод и показываем его ТОЛЬКО при падении — иначе печатаем
# одну строку. С -v отдаём вывод как есть (для отладки конкретных тестов).
cd "$REPO_ROOT"
if [[ -n "$verbose" ]]; then
  python3 -m unittest discover -s tests -p "test_*.py" -v
else
  out="$(python3 -m unittest discover -s tests -p "test_*.py" 2>&1)" || {
    echo "$out" >&2
    echo "ERROR: тесты упали" >&2
    exit 1
  }
  echo "tests: OK ($(echo "$out" | grep -oE 'Ran [0-9]+ tests' | head -1))"
fi
