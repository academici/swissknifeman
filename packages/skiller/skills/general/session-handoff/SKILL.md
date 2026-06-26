---
name: session-handoff
bucket: general
version: 0.1.0
description: "Cross-session/agent context handoff: compress a session into a structured doc — state, decisions, open items, next steps."
risk: draft
persona: oss-dev
tags: [workflow, context, tokens, handoff]
requires: []
produces_for: []
outputs: []
snippets: ["handoff-template.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Session Handoff

## Activate when
- Session context near limit (or compaction imminent).
- Work handed to another agent (Claude → Cursor, local → CI).
- `anti-drift` hard threshold tripped — end session, restart.
- End of workday on a multi-day task.

## Protocol
1. **Gather state.** `git status` + `git diff --stat`: changed / committed / in-progress. From the repo, not memory.
2. **Record decisions.** Each decision with rationale ("chose X because Y; considered Z, rejected for W"). A decision without "why" is useless.
3. **List open items.** Open questions, known bugs, deferred edits — note what blocks each.
4. **Next steps.** Concrete actions in priority order, with file paths and verification commands.
5. **Read-from-scratch check.** Reread as a context-less agent: understandable without this session? Codenames/abbreviations introduced this session — expand or remove.

## Doc structure
Template: `snippets/handoff-template.md`. Save per project convention (e.g. `docs/handoff/YYYY-MM-DD-<topic>.md`) or pass in first message of new session.

## Anti-patterns
- Summary from memory without `git status`/`git diff`.
- Listing done work without "why" on decisions.
- Dumping whole session log — this is compression, not a transcript.

## Related skills
- `anti-drift` (general) — after hard threshold, session ends with this handoff.
- `context-economy` (general) — handoff before `/clear` as part of Plan→Clear→Execute.
- `complex-task-orchestrator` (general) — open subtasks and risks go into the handoff.
- `system/shared-memory` — if projects share memory, key facts go there (remember), not only the handoff file.

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 3ae40e6a17d3f0633f39f51043afdc0c37c62389693ff079bd87515c517e7423 -->
