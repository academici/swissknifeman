#!/usr/bin/env bash
# Compatibility shim for Codex sessions that cached the removed bootstrap
# PreToolUse/ExitPlanMode registration. Codex-native approval_policy and
# sandbox_mode own access decisions; this shim intentionally grants nothing.

cat >/dev/null
exit 0
