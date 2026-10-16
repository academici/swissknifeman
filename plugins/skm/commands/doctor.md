---
description: Diagnostics of every swissknifeman module (skiller, maind, harness, planner, orch ...), read-only.
argument-hint: "[--unit ID ...] [--category environment|config|state|content|integration]"
allowed-tools: Bash(swissknifeman:*), Bash(skiller:*)
---
## Diagnostics (swissknifeman doctor)
!`swissknifeman doctor $ARGUMENTS`

Explain the failed checks (FAIL) with the remediation each one prints and offer to apply it; the doctor itself repairs
nothing. Only the skill registry: `skiller doctor`. Related: `/skm:status`, `/skm:skills`.
