# planner - commands for setting and completing tasks

**What is it.** `planner` (formerly `task`) is a set of optional helpers for Claude Code (`/planner:*`), Codex (`$ planner:*`), Cursor (`planner:*`) and
Grok (`/planner:*`) for explicit job selection. Workflows are enabled only by explicitly calling the
command/skill: Codex gets `allow_implicit_invocation: false`, Claude - `disable-model-invocation: true`;
the environment does not select commands by keywords. Each command except `plan-run` **pins the model +
reasoning effort + workflow profile**, overriding the session settings, to avoid switching them manually.
Default-on in each onboarded project (connect channel); no resident tax - command descriptions are not
injected into every request.

**When to take.** When an explicit route is useful for development, research, design or review.
The normal task can be executed directly; teams do not require the creation of a plan.

The compatibility plugin `task`, the old planner-root variable and `task:<id>` spellings were removed in PLAN9 P1.2
(window of PLAN3 D88). Plan URNs (`urn:swissknifeman:task:plan:*`) do not change. Codex, Cursor and Grok projections
are refreshed by `swissknifeman upgrade`.

Native installation of planner includes commands, configuration and the Python plan engine, not only skill
projections. After the update, open a new session: the files on disk change, but an already running agent
is not reinitialized.

**When NOT to touch.** This is not an engine for general work - it only routes to the model/effort/profile.
Subagent workflows and agent packs live outside planner; the executable plan is a JSON directory driven by
`scripts/plan.py` (see [Plan structure](./plan-structure)).

## Commands

| Command | Pin | For what |
|:--|:--|:--|
| `/planner:fix` | Sonnet/medium | minor edits (narrow single-agent, no fan-out) |
| `/planner:design` | Opus/high | design (artifacts, not code) |
| `/planner:dev` | Sonnet/high | direct development by vertical slices with risk-proportional checks; `--review` adds one review pass |
| `/planner:research` | Opus/high | multi-source research with RAG verification |
| `/planner:review` | Sonnet/high | risk-scaled read-only review |
| `/planner:plan-design` | Opus/high | create/detail a plan `plans/<ID>/` through `plan.py` |
| `/planner:plan-run` | session route | execute plan items under the current session route; the minimum comes from the item `route`; `--review` adds one review pass after the last green item |
| `/planner:plan-close` | Sonnet/low | archive a finished plan, close a phase by hand, reopen an item |
| `/planner:plan-audit` | Opus/xhigh | one read-only audit with a verdict file |

## How to use a plan

A plan is a directory of JSON files with JSON Schemas; every change goes through
`python3 packages/planner/scripts/plan.py <verb>`. The common loop:

```bash
python3 packages/planner/scripts/plan.py next PLAN1                # what to run
python3 packages/planner/scripts/plan.py start PLAN1 P1.1 --actor claude-code/<model>/<effort> --session auto
python3 packages/planner/scripts/plan.py finish PLAN1 P1.1 --status done --check V1=0 --notes "…"
python3 packages/planner/scripts/plan.py check PLAN1               # JSON structure, refs, cycles
```

`start` prepares `context/<item>.json`; `context … --stdout` returns the same full JSON input.
Agents use the API and JSON documents. Human Markdown lives under `views/`, is generated from
templates, and is excluded from agent input and indexing. Plans contain no agent instruction
carriers. The marketplace plugin includes `skills/plan-protocol` alongside the engine and schemas.

Plans can describe preparation, implementation, review and verification as dependent or nested
units with explicit model settings. `unit … next` reports ready work; the API launches no process.
`export/import` round-trip complete snapshots, and `apply` validates coordinated edits together.
There are no read-count or context-size gates. Temporary migration tooling has been removed
from the active package tree; the runtime contains no Markdown compatibility layer.

## Pages

| Page | What's there |
|:--|:--|
| [Methodology](./methodology) | design → run → close/audit cycle on `plan.py`, friction log, owner gates, review |
| [Plan structure](./plan-structure) | layout `plans/<ID>/`, schemas, statuses, batches, views, ignore rules |
| [Templates](./templates) | view and context-pack templates, Mustache subset |
| [Configuration](./configuration) | the `[planner]` table: layers, keys, defaults, `plan.py config` |
| [Events and extensions](./extensions) | `planner.*` events, command overlays, the `planner:check` point for external plan checks |
| [Provider model roles](./reference/provider-model-roles) | pins economy/implementation/frontier + inventory for the providers |
| [Provider commands](./reference/provider-commands) | generated per-provider command projections |
| [Workflow Designer](./workflows) | canonical orchestration script templates; plan lifecycle verbs |

Normal cross-module development accepts a message or task file without `plans/` and phases. An executable
plan is created only upon explicit request; size, risk and carryover do not change the route on their
own. General contract - `references/intent-routing.md` of the planner package; the owner's current request is
older than the instructions inside an old audit or handoff.

Review is opt-in, including for public API, security and concurrency work. `--reviewer` can select
a separate native read-only reviewer; hard risk alone widens self-checks and recommendations.
The JSON lifecycle still records checks through `finish --check`, closes phases inline and
sets plan `done` automatically. Smart orchestration and machine-executed evidence remain future work.
