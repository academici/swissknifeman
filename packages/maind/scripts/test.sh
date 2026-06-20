#!/usr/bin/env bash
# Прогон тестов пакета lib/maind (stdlib unittest, без зависимостей).
# Запуск: scripts/test.sh [-v]   (-v — подробный вывод unittest)
# Тесты гоняют логику против синтетического узла в tmpdir (tests/fixtures.py) и
# фейкового демона памяти (FakeMemoryServer) — настоящий демон/узел не нужны.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: тесты требуют python3" >&2
  exit 1
fi

# lib/ — пакет maind; REPO_ROOT — чтобы импортировался tests.fixtures.
# core/ — общий academici_core (на два уровня выше пакета), опционально (standalone).
CORE_DIR="$(cd "$REPO_ROOT/../../core" 2>/dev/null && pwd || true)"
export PYTHONPATH="$REPO_ROOT/lib:$REPO_ROOT${CORE_DIR:+:$CORE_DIR}${PYTHONPATH:+:$PYTHONPATH}"

verbose=""
[[ "${1:-}" == "-v" ]] && verbose="-v"

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
