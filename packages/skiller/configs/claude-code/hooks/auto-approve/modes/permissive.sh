#!/usr/bin/env bash
# Режим PERMISSIVE (denylist-first): «что явно не запрещено — разрешено».
# Риск: незнакомая команда вне денилиста будет одобрена. Только доверенный проект.
[ "$HOOK_TOOL" = "Bash" ] || fallthrough
prepare_bash || fallthrough
HOOK_NAME="auto-approve(permissive)"
run_bash_analysis permissive
