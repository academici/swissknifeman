# Semantics loop'ov: iterative execution on top of skills

How the agent should perform the task **iteratively with checking on each circle**, not
creating a separate entity registry for this. The document formulates the model loop'ah,
shows which **existing** it is already closed with skills, and where does it go
boundary between skill (policy: *what to check and when to stop*) and runner
(mechanics: *the loop itself*).

The idea was inspired by the catalog [loops.elorm.xyz](https://loops.elorm.xyz/loops) — dial
reused «loop'ov» for AI-agents. It is useful not for file organization, but
a compact execution model that should be taken as a vocabulary rather than a structure.

## Model loop'a

Everyone loop specifies five fields plus protection against «cheating»:

| Field | Meaning |
|---|---|
| **Goal** | objective result («PR open, all CI-checks are green») |
| **Run mode** | manual (prompt-only) or by event (hook) |
| **Max iterations** | upper limit of circles (usually 3–12) — loop insurance |
| **Between-iterations check** | command used by the agent to check progress between laps (`git log`, test, lint) |
| **Exit condition** | objective state = task completed |
| **Step 1** | what the agent does on each circle |

**Anti-gaming guardrails** (this is not in regular checklists, but this is what makes it different
loop from «just repeat»): you cannot change the check itself for it to pass; it's impossible
skip verification; You can’t fake success by manipulating metrics. Exit
condition is assessed by the conclusion of a fair test, not by the agent's assertion.

## The runner is already built in - skills are given by gates, not a cycle

The cycle itself does not need to be executed in skill prose: Claude Code already gives
runner.

- **`/loop`** — self-paced or by interval; the agent maintains the pace himself, after
  of each circle runs a check and continues only if exit condition not
  reached.
- **`/schedule`** — cron-agents for repetitive tasks (CI, audit, sync).
- `ScheduleWakeup` — dynamic tempo inside `/loop` to wait for external
  states.

Registry skills give **contents** loop'a: purpose, what is considered a check, under what
signal to stop. The runner is given built-in commands. Therefore, there is no
we need a prose-pseudo-runner, duplicated in each skill.

## Mapping to existing skills

Model loop'and has already been divided into mature skills - each closes its own phase:

| Phase loop'a | Skill | What gives |
|---|---|---|
| Pre-loop contract | [`general/task-brief-template`](https://github.com/academici/swissknifeman/blob/main/skills/general/task-brief-template/SKILL.md) | Goal, out-of-scope, fields `Loop verifier`/`Exit condition`/`Hard stop trigger`, DoD |
| Stop-controller | [`general/anti-drift`](https://github.com/academici/swissknifeman/blob/main/skills/general/anti-drift/SKILL.md) | Circuit Breaker (soft ~10 tool-calls / hard ~20 iterations), degradation signals, hard-stop → handoff |
| Between-iterations verifier | [`general/cross-layer-change-checklist`](https://github.com/academici/swissknifeman/blob/main/skills/general/cross-layer-change-checklist/SKILL.md) | checking affected layers (Domain/API/Frontend/Data/Docs/Tests) after significant change |
| Simplification gate | [`quality/code-simplifier`](https://github.com/academici/swissknifeman/blob/main/skills/quality/code-simplifier/SKILL.md) | YAGNI-checklist before announcement «ready»: roll back unnecessary abstractions |
| Independent verifier | [`quality/code-review`](https://github.com/academici/swissknifeman/blob/main/skills/quality/code-review/SKILL.md), [`oss-dev/gh-review`](https://github.com/academici/swissknifeman/blob/main/skills/oss-dev/gh-review/SKILL.md) | independent verification diff/tests/docs, not trust «is already correct» |
| Shared-code gate | [`architect/package-contribution-protocol`](https://github.com/academici/swissknifeman/blob/main/skills/architect/package-contribution-protocol/SKILL.md), [`architect/architecture`](https://github.com/academici/swissknifeman/blob/main/skills/architect/architecture/SKILL.md) | stop before premature removal to the general layer (Rule of Three, ADR) |
| Phase orchestration | [`general/complex-task-orchestrator`](https://github.com/academici/swissknifeman/blob/main/skills/general/complex-task-orchestrator/SKILL.md) | decomposition into phases with deliverables and test-gate between them |
| Long-loop discipline | [`general/context-economy`](https://github.com/academici/swissknifeman/blob/main/skills/general/context-economy/SKILL.md) | Plan→Clear→Execute, `/compact`, separate sessions for long cycles |
| Leaving the circle | [`general/session-handoff`](https://github.com/academici/swissknifeman/blob/main/skills/general/session-handoff/SKILL.md) | compressed handoff when hard-stop, new session with clean context |

Loop-aware execution is **link** of these skills, not a new artifact.
Starting template that accomplishes the goal/check/exit/hard-stop into one kickoff —
snippet `loop-kickoff.md` skill `task-brief-template` (is copied to
`.claude/commands/` project like `command-*` snippets `context-economy`).

## Why is there no folder `loops/`

Same anti-bloat, as in [methodologies against code bloat](./methodology):
loop-semantics lives **inside canonical-skill**, and not in the parallel registry.

- Separate `loops/`-registry = second index next to skills → duplicates of one
  pattern in two places and divergence SSOT.
- Incorporate a prose cycle into every skill = bloat; The runner is already built in.
- Folder `loops/` is only justified if execution-pattern will become independent
  reusable-a unit that is really cramped within the existing skills. On the current
  stage there is no such thing.

The solution is fixed as an invariant: **first we strengthen a mature skill, and only when
proven necessity, we create a new entity.**

## Example: doc/changelog-sync loop

Specific loop from catalog - synchronization CHANGELOG after change - goes down
exactly release-discipline of this repository:

```text
Goal:            CHANGELOG.md [Unreleased] accurately covers all visible changes
Run mode:        manual
Max iterations:  3
Between-check:   git log $(git describe --tags --abbrev=0 2>/dev/null || echo HEAD~20)..HEAD --oneline
Exit condition:  changelog covers everything user-visible changes
Step 1:          view recent commits → add Keep-a-Changelog entries → check completeness
```

Verifier here is a layer Docs from `cross-layer-change-checklist`; stop-controller —
`anti-drift`; exit is assessed by fair conclusion `git log`, not as stated
agent (anti-gaming).

## When to enable loop-aware mode

1. First look for the right one existing skill.
2. Check if he has loop-semantics: exit criterion, check between
   in circles, hard-stop. If the task requires **more than one meaningful iteration with
   intermediate check** — fill in the fields loop in `task-brief-template` and
   run via `/loop`.
3. If the required semantics in canonical-no skill - suggest **add it to this
   skill**, rather than starting a new one top-level entity.

## Sources

- [loops.elorm.xyz/loops](https://loops.elorm.xyz/loops) — reusable directory
  loop'ov for AI-agents (model Goal/Run mode/Max iterations/Between-check/Exit).
- [loops.elorm.xyz/loops/changelog-sync-after-ship](https://loops.elorm.xyz/loops/changelog-sync-after-ship) — specific loop, on which the example above is based.
- [Methodology: against code bloat](./methodology) — general principle «ask before expanding», on which the waiver is based `loops/`-registry.
