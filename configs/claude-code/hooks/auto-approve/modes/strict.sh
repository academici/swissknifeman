#!/usr/bin/env bash
# Режим STRICT (allowlist-first): «что явно не разрешено — на обычный промпт».
# Источается переключателем auto-approve.sh (common.sh + analyze.sh уже загружены).
[ "$HOOK_TOOL" = "Bash" ] || fallthrough
prepare_bash || fallthrough
HOOK_NAME="auto-approve(strict)"
run_bash_analysis strict
