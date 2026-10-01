---
description: Deep analysis of runs by an analyst agent (digest-first) — scripts are collected JSON-extracts, the agent constructs a causal narrative; raw-transcripts are not allowed.
argument-hint: "[parsing focus: «why is it expensive», «resolve CONFLICT», «role degradation X», …]"
allowed-tools: Bash(mkdir:*), Bash(maind:*), Bash(analyst:*), Read, Write, Task
---
## Collecting marc (digest-first — agent will receive ONLY these JSON)
!`mkdir -p .claude/analyst/deep`
!`maind analyze --cwd --json > .claude/analyst/deep/analyze.json 2>&1 || true`
!`analyst token-report --json > .claude/analyst/deep/token-report.json 2>&1 || true`
!`analyst review --json > .claude/analyst/deep/review.json 2>&1 || true`

The three commands above have already worked and recorded the extracts in `.claude/analyst/deep/`
(`analyze.json`, `token-report.json`, `review.json`). Next:

1. **Start subagent `analyst`** (Task, subagent_type `analyst`). In the prompt, pass:
   - **paths** to three JSON-files (`.claude/analyst/deep/analyze.json`,
     `.claude/analyst/deep/token-report.json`, `.claude/analyst/deep/review.json`) —
     exactly the paths, NOT the contents;
   - parsing focus from user: «$ARGUMENTS» (empty - full playbook:
     cost/pathologies, hidden scope expansion, quality handoff, degradation
     cheap-models, resolve CONFLICT-lessons, texts remediation).
   **Prohibited** (for both you and the subagent): read raw-session transcripts
   (`~/.claude/**/*.jsonl` and any session-logs) and transfer their contents -
   agent input only extracts; if any of the files contains error text
   instead JSON (for example, no usage-trend) — say so, the agent will take into account the data gap.

2. **Accept the agent's result**: causal narrative + block findings JSON
   (schema - contract `analyst ingest`, see agent description).

3. **Save findings** in `.claude/analyst/deep/findings.json` (exactly the same JSON,
   what the agent returned, without edits) and do:
   `analyst ingest --file .claude/analyst/deep/findings.json`
   Empty findings (`"findings": []`) — ingest don't run it, tell the owner so.

4. **Show to owner**: agent narrative, summary ingest (how many lessons in ephemeral,
   how many were missed as duplicates), finds with marker PROMOTE-CANDIDATE — separate
   list with a reminder that the promotion is done only by a person:
   `analyst review` → `analyst promote <id>`.

Invariants: no auto-promotion (all agent lessons - only ephemeral, gate - human);
raw materials remain LOCAL (out - numbers and abstractions). Command on-demand — after episode
ATTENTION or weekly, not per-session.

> Required CLI `analyst` and `maind` in PATH (repository swissknifeman → `./install.sh`).
