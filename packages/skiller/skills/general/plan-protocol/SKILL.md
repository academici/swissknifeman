---
name: plan-protocol
bucket: general
version: 3.0.0
description: "Use when an explicitly invoked Task plan command needs a plan layout, status or verb reference."
when_to_use: "Only after explicit Task invocation, when a named plan schema detail is needed."
disable-model-invocation: true
risk: write
persona: oss-dev
tags: [workflow, planning, handoff, routing, multi-model]
requires: []
produces_for: [session-handoff, complex-task-orchestrator]
outputs: ["plans/<PLAN-ID>/plan.json", "plans/<PLAN-ID>/phases/", "plans/<PLAN-ID>/log.jsonl"]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Plan Protocol

Canon version: `plan-protocol-v3`. Plans are JSON documents changed only through the `plan.py` API
(`python3 <Task package root>/scripts/plan.py`). Python validates every change and regenerates the
Markdown views. Activate only for an explicit `task:plan-design`, `task:plan-run`, `task:plan-close`
or `task:plan-audit` invocation; ordinary work never needs a plan.

## 1. Layout

```text
plans/<YYYY.MM.DD-№N-CODENAME>/
  plan.json  brief.json  log.jsonl  .gitignore          # sources
  phases/<Pn>/phase.json  phases/<Pn>/<Pn.m>.json       # sources
  phases/<Pn>/<Pn.m>/<U#>.json                          # units (optional)
  decisions/<D#>.json                                   # sources
  research/  artifacts/                                 # supporting files, hand-written
  index.md plan.md roadmap.md status.md handoff.md open-questions.md AGENTS.md CLAUDE.md   # generated
  context/<Pn.m>.md                                     # generated context packs (git-ignored)
```

Generated files are never edited and are not read for work; get state with `plan.py next|show|context`.
Schemas: `<Task package root>/schemas/plan/v1/*.schema.json` (`urn:swissknifeman:task:plan:<kind>:v1`).
`plan.py check` is the only validator; it also reports stale views (`plan.py render` repairs them).

## 2. Identity and references

- Directory id `YYYY.MM.DD-№N-CODENAME`, title `Plan №N — …`, Short ID `PLAN<N>`: allocated by
  `plan.py new`, never guessed, never recycled; archived plans keep theirs.
- Local ids: phase `P<n>`, item `P<n>.<m>`, decision `D<n>`, unit `P<n>.<m>/U<k>`.
- Outside the plan directory qualify ids: `PLAN<N>.P2.3`, `PLAN<N>.D4`; across repositories
  `<repo>:PLAN<N>.D4`. Details: [references/work-references.md](references/work-references.md).
- Paths in plan JSON are repository-relative or `@plan/…` (inside the plan directory).

## 3. Statuses

Item `status` (EXACTLY these six): `todo`, `in_progress`, `done`, `done_with_deviations`, `blocked`,
`skipped`. Terminal: the last four. Satisfying a dependency: `done`, `done_with_deviations`, `skipped`.
Phase `design`: `skeleton` → `detailed` (`plan.py design-done`); phase `closed` is written by
`finish` when its last item ends (worst-of result). Plan `status`: `active` → `done` → `archived`.
Decisions: `open` → `accepted` (`plan.py decide`) or `superseded`.
`status`, `result`, `design`, `closed` and identity fields are lifecycle-owned: authoring verbs refuse
them with `FIELD_OWNED`.

## 4. Routing

An item's `route` (`class`: `economy|implementation|frontier`, `effort`: `low|medium|high|xhigh`) is the
minimum. The executor runs under its own session route and declares it with `start --actor
<provider>/<model>/<effort>`; a weaker route is refused (`ROUTE_UNDERSHOOT`), a stronger one is
allowed. Provider model pools live in `configs/command-routing.json`. A batch runs at the maximum
route of its members. `plan-run` never pins a model.

## 5. API verbs

| Purpose | Verbs |
|:--|:--|
| author | `new`, `set`, `push`, `add-phase`, `add-item`, `add-decision`, `batches`, `design-done` |
| inspect | `show [<ref>] [--json]`, `next [--json]`, `context <item> [--stdout]`, `check [--json]`, `render [--check]` |
| execute | `start <items…> --actor …`, `log <ref> --type …`, `finish <item> --status … --check V#=<exit>` |
| owner | `decide`, `supersede`, `grant <GATE> --note …`, `reopen`, `archive` |

`next` returns exactly one semantic step: `design-phase`, `run-items` (a ready batch with its
route), `waiting` (dependency, gate, open decision, blocked item), `archive`, or `terminal`.
`start` writes `context/<item>.md`: goal, scope, context, decisions, upstream results, reads (with
inlined sections), files, lessons, rules and done-when — the executor's whole input.
`finish --status done` needs every acceptance check recorded with exit 0.
Friction (`log --type deviation|blocker|difficulty|assumption|note`) is written only when reality
changes the plan, an assumption or a blocker; it feeds the next items' Lessons.
Exit codes: 0 ok, 1 refusal or check errors (`CODE: message` on stderr), 2 usage.

## 6. Design rules

- A detailed item has summary, why, scope include, reads or task_files, at least one acceptance
  check with an exact command, and deliverables (`check` enforces this).
- Long reasoning, algorithms, worked examples live in `research/`/`artifacts/` and are referenced
  from item `reads` with a `section`, so the pack inlines exactly what is needed.
- Batches group items that share files or context; `mode: required` only for an atomic group.
- Owner gates: `authority: {kind: owner_gate, gate: X}`; `start` refuses until `plan.py grant X`
  records the owner's message.

## 7. Review and audit

Review is opt-in: items use `review: {mode: none}` (self-check plus affected tests). `--review` or an
explicit owner request adds one read-only review item at the end of the scope. `task:plan-audit`
runs only on explicit owner invocation and writes a verdict file plus a `note` event.

## References

- [references/common-principles.md](references/common-principles.md) — shared rules for every plan command.
- [references/design-mode.md](references/design-mode.md), [references/execution-mode.md](references/execution-mode.md),
  [references/review-mode.md](references/review-mode.md) — per-command notes.
- [references/work-references.md](references/work-references.md) — Short IDs and qualified references.
