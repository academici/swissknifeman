# task - commands for setting and completing tasks

**What is it.** Optional helpers for Claude Code (`/task:*`), Codex (`$ task:*`), Cursor (`task:*`) and
Grok (`/task:*`) for explicit job selection. Workflows are enabled only by explicitly calling the
command/skill: Codex gets `allow_implicit_invocation: false`, Claude - `disable-model-invocation: true`;
harness does not select commands by keywords. Each command except `plan-run` **pins the model +
reasoning effort + workflow profile**, overriding the session settings, to avoid switching them manually.
Default-on in each onboarded project (connect channel); no resident tax - command descriptions are not
injected into every request.

**When to take.** When an explicit route is useful for development, research, design or review.
The normal task can be executed directly; teams do not require the creation of a plan.

Native installation of Task includes commands, configuration and the Python plan engine, not only skill
projections. After the update, open a new session: the files on disk change, but an already running agent
is not reinitialized.

**When NOT to touch.** This is not an engine for general work - it only routes to the model/effort/profile.
Subagent workflows and agent packs live in `harness`; the executable plan is a JSON directory driven by
`scripts/plan.py` (see [Plan structure](./plan-structure)).

## Commands

| Command | Pin | For what |
|:--|:--|:--|
| `/task:fix` | Sonnet/medium | minor edits (narrow single-agent, no fan-out) |
| `/task:design` | Opus/high | design (artifacts, not code) |
| `/task:dev` | Sonnet/high | direct development by vertical slices with risk-proportional checks; `--review` adds one review pass |
| `/task:research` | Opus/high | multi-source research with RAG verification |
| `/task:review` | Sonnet/high | risk-scaled read-only review |
| `/task:plan-design` | Opus/high | create/detail a plan `plans/<ID>/` through `plan.py` |
| `/task:plan-run` | session route | execute plan items under the current session route; the minimum comes from the item `route`; `--review` adds one review pass after the last green item |
| `/task:plan-close` | Sonnet/low | archive a finished plan, close a phase by hand, reopen an item |
| `/task:plan-audit` | Opus/xhigh | one read-only audit with a verdict file |

## How to use a plan

A plan is a directory of JSON files with JSON Schemas; every change goes through
`python3 packages/task/scripts/plan.py <verb>`. The common loop:

```bash
python3 packages/task/scripts/plan.py next PLAN1                # what to run
python3 packages/task/scripts/plan.py start PLAN1 P1.1 --actor claude-code/<model>/<effort> --session auto
python3 packages/task/scripts/plan.py finish PLAN1 P1.1 --status done --check V1=0 --notes "…"
python3 packages/task/scripts/plan.py check PLAN1               # structure, refs, cycles, fresh views
```

`start` prepares `context/<item>.md` - everything the executor needs; read only that file and the reads
it lists. The Markdown views (`index, plan, roadmap, status, handoff, open-questions`) and the plan-local
`AGENTS.md`/`CLAUDE.md` are generated and regenerated after every change: never edit or read them for
work. A tool failure does not open a new design cycle: the executor repairs the reversible cause in the
same attempt and records only real friction with `plan.py log`.

Old Markdown (layout v2) plans are migrated once by hand with
[the migration instruction](./migration/v2-to-v3.md); the v3 engine does not read them.

## Pages

| Page | What's there |
|:--|:--|
| [Methodology](./methodology) | design → run → close/audit cycle on `plan.py`, friction log, owner gates, review |
| [Plan structure](./plan-structure) | layout `plans/<ID>/`, schemas, statuses, batches, views, ignore rules |
| [Templates](./templates) | view and context-pack templates, Mustache subset |
| [Provider model roles](./reference/provider-model-roles) | pins economy/implementation/frontier + inventory for the providers |
| [Provider commands](./reference/provider-commands) | generated per-provider command projections |
| [Workflow Designer](./workflows) | canonical orchestration script templates; plan lifecycle verbs |

Normal cross-module development accepts a message or task file without `plans/` and phases. An executable
plan is created only upon explicit request; size, risk and carryover do not change the route on their
own. General contract - `references/intent-routing.md` of the Task package; the owner's current request is
older than the instructions inside an old audit or handoff.
