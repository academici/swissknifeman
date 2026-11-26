---
description: Post-run analysis of the CURRENT project run «did everything work?» — run-report + bash-log + git + health → verdict GREEN/ATTENTION/RED.
argument-hint: "[--session UUID] [--base BRANCH]"
allowed-tools: Bash(maind:*)
---
## Parsing a run (current directory)
!`maind analyze --cwd --json $ARGUMENTS`

Parse the result and give the owner a short summary:
- **`verdict`** (GREEN / ATTENTION / RED) + `confidence` (`low` = no run-report, forensic output - suggest enabling a hook `harness hooks --target . --run-report on`).
- **`red`** — that fell (tests/work flow): listed explicitly, these are blockers.
- **`reasons`** — what to pay attention to (lint, tool-failures, deferred/workarounds, dirty tree, observer-alerts).
- **`repass`** — block «Unverified → REPEAT PASS»: where is the engine (RAG/tool) was not available during formation - suggest a repeat pass on these points.
- Briefly: `run_report` (tests/lint/files/work flow), `git` (is the tree clean), `health` (hub is alive).

If `verdict` = RED — name the blockers and suggest what to fix. If ATTENTION with non-empty `repass` — suggest repeating the collection of data on these facts (in line RAG-disciplines: plan 100% based on fresh data).
