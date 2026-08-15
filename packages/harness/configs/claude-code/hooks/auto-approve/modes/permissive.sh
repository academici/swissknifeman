#!/usr/bin/env bash
[ "$HOOK_TOOL" = "Bash" ] || fallthrough
prepare_bash || fallthrough
HOOK_NAME="auto-approve(permissive)"
run_bash_analysis permissive
