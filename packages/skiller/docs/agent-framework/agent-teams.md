# Agent Teams (Mesh) — optional layer

> Status: experiment Claude Code (first-party `https://code.claude.com/docs/en/agent-teams`,
> verified 2026-07-29). **Prerequisite: CC ≥ 2.1.178** (page describes the behavior «by
> as of» this version, not an availability threshold; not available on 2.1.158). Config
> forward compatible - flag and team-events on the old version are simply not active, nothing
> are broken. **Default `teammateMode` changed from `auto` on `in-process` with v2.1.179**; `iterm2`
> as explicit mode - with v2.1.186 (requires `it2` CLI).

## What is it and when

Agent Teams — multiple independent sessions Claude, communicating mesh-style (direct
messages + broadcast) via general task list, and not just through the orchestrator. Difference
from subagents: teammates are completely independent and self-coordinated; more expensive (~3-4x
tokens).

| Take Agent Teams | We remain on subagents/workflow |
|---|---|
| Unlinked layers at the same time (API+front+tests) | Sequential task / tight deps |
| Competing hypotheses (debug) | Only parallelization without communication is needed |
| Architectural debate between agents | Token budget limited |

Framework roles (`reviewer`/`implementer`/`test-writer`/`spec-writer`) **are suitable as
teammates** no changes - the same `.claude/agents/*.md`. **Disclaimer:** fields `skills` and
`mcpServers` subagent definitions in this mode **do not apply** — teammates loading
skills/MCP-servers from project/user settings session as a normal session, not from
agent definitions (first-party `https://code.claude.com/docs/en/agent-teams`, verified
2026-07-29); only works self-load fallback in the body of the role ([roles](./roles)).

## Enable (opt.)

Add preset (merge-only) `harness/configs/claude-code/settings.agent-teams.json`:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" }, "teammateMode": "auto" }
```

`teammateMode`: `in-process` (one terminal, **default with v2.1.179**) | `auto` (split when
tmux/iTerm2, default was before v2.1.179) | `tmux` | `iterm2` (with v2.1.186, requires `it2` CLI).
Config coexists with PreToolUse(auto-approve)/SubagentStop(review-gate) — events are different,
no conflict.

## Quality-gate hooks (optional, after upgrade CC)

Official team events - **`TeammateIdle`, `TaskCreated`, `TaskCompleted`**
(`TeamCreate`/`TeamDelete` no longer exist; `team_name` on Agent-thule is accepted and
is ignored, first-party `https://code.claude.com/docs/en/agent-teams`, verified
2026-07-29) — you can add the same check as review-gate (exit 2 → task not
completes, agent repairs). Add to `.claude/settings.json` append-if-absent, when CC
has been updated and can be tested:

```json
{ "hooks": { "TeammateIdle": [ { "hooks": [ { "type": "command",
  "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/review-gate.sh" } ] } ] } }
```

## Module-boundaries (conflict avoidance)

Parallel teammates should NOT be written to the same file. Coordination through task list, NOT
file-lock (`touch *.lock` rejected as fragile). B `.ai/guidelines/` project (in Boost —
not generated CLAUDE.md) fix the zones:

```
- app/Http/, app/Actions/, app/Repositories/  → backend-role
- resources/js/, pages/                        → frontend-role
- tests/                                        → test-writer
- General models/routes: one owner per run; intersection - sequentially
  or worktree-isolation, non-parallel write.
```

## Spawn-templates

**Full-stack feature:**
```
Spawn 3 teammates:
1. backend-implementer: API-endpoint
2. frontend-implementer: front for endpoint
3. reviewer: review of both diffs (over-engineering + canon)
Require plan approval before changes.
```

**Parallel debug:**
```
Spawn 2 teammates (read-only) for a bug <description>:
1. hypothesis-a: checks <reason A>
2. hypothesis-b: checks <reason B>
Exchange finds, return lead single output.
```

## Limitations

- Experimental (CC ≥2.1.178); resume does not save team config (task list persistent).
- Teammate-model does not inherit `/model` lead - indicate explicitly in spawn; **effort lead
  is inherited** in split-pane modes with v2.1.186 (first-party
  `https://code.claude.com/docs/en/agent-teams`, verified 2026-07-29).
- There are no nested commands; lead is fixed; split-pane requires tmux/iTerm2.
- Recommended team size: 3-5 teammates, 5–6 tasks on teammate.
- Broadcast roads - only direct messages, broadcast as an exception.
- file-lock protocol - DO NOT use (rejected); zones via module-boundaries.
