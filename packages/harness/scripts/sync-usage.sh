#!/usr/bin/env bash
# sync-usage.sh — вендорит core/usage.py байт-в-байт в run-report хук (_usage.py).
#
# run-report-хук копируется в ~/.claude/hooks/run-report (см. apply-permissions.sh
# --global) БЕЗ PYTHONPATH монорепо — модуль usage должен физически лежать рядом с
# _lib.py/run-report.py, а не импортироваться из core/. core/usage.py — источник
# истины (самодостаточный, stdlib-only, без «from core...»/«from .» — см. его
# докстринг); этот скрипт — единственное место, где происходит копия.
#
# Запускать вручную после ЛЮБОЙ правки core/usage.py — validate.sh (cmp-гейт)
# роняет сборку, если вендоренная копия разошлась с источником.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"                 # packages/harness
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." && pwd)"           # корень swissknifeman

SRC="$MONOREPO_ROOT/core/usage.py"
DST="$REPO_ROOT/configs/claude-code/hooks/run-report/_usage.py"

[[ -f "$SRC" ]] || { echo "Ошибка: не найден $SRC" >&2; exit 1; }

cp "$SRC" "$DST"
echo "sync-usage: $SRC → $DST"
