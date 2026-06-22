#!/usr/bin/env bash
# test.sh — unittest пакета harness (без сети; временные каталоги).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# MONOREPO_ROOT (на два уровня выше пакета) — чтобы импортировался пакет `core`.
# Fallback на standalone-раскладку: если каталога core нет — путь не добавляется.
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""

PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest discover -s "$REPO_ROOT/tests" -t "$REPO_ROOT" "$@"
