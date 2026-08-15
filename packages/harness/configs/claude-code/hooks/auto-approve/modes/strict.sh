#!/usr/bin/env bash
[ "$HOOK_TOOL" = "Bash" ] || fallthrough
prepare_bash || fallthrough
HOOK_NAME="auto-approve(strict)"
run_bash_analysis strict
