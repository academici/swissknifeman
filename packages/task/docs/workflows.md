# Task workflow template constructor

Subagent orchestration is not written from scratch for each task: canon - **4 parameterizable
script template** in `packages/task/workflows/` + rules for filling slots (README folder).
This is a library of portable templates, NOT a code generator and NOT a new DSL - workflow script
is already quite expressive; the constructor only captures proven topologies.

## When which template

| Template | Orchestration | Slots | Take when |
|:--|:--|:--|:--|
| `wf-research-fanout.js` | N topics × research → adversarial verify (pipeline, no barrier) | `TOPICS[]`, answer schemes, model/effort | multi-topic research with verification: market, stack, RAG under plan |
| `wf-author-by-spec.js` | spec → N file tasks × author → self-check (pipeline) | `FILES[]` (file + TK + validation), pipeline-commands | Stage-3 authoring using a ready-made spec: skills, docks, commands per-file |
| `wf-audit-adversarial.js` | M finders → dedup → adversarial verify → verdicts | `DIMENSIONS[]`, severity-enum, profile constitution | audit/review of artifact by measurements: plan, code, documentation |
| `wf-dev-slice.js` | slice → impl → tests-to-green → optional review (REVIEW slot, off by default) | `SLICES[]`, gates | development by vertical slices (profile `/task:dev`) |

Sample prototype: `wf-p5-research.js` ECOSYSTEM P5 plan - working copy of template 1.

## Slot Rules

- **Slots are only constants in the script header.** Parameterization for editing the header, not
  args-string: embedded-config instead of parsing arguments (named-workflow trap -
  the line of arguments breaks on the very first multi-line TK).
- **The supervisor holds the context, the agents return structured summaries with the schema.**
  Handoff between stages - artifact-centric: file/structure, not chat retelling.
- **Judge-panel (3+ verdicts) - slot only for high-stakes stages.** Default
  single-agent: it closes most tasks, the panel of judges is selective (fiscal,
  payments, public contracts).
- **`max-iteration` is required for any loop-until** - a loop without an upper bound is prohibited.
- In `wf-dev-slice.js` commit is performed only after green tests, interslice gates and (only when the
  `REVIEW` slot is enabled) independent review. The missing result of impl/fix/review/gate/commit stops the workflow and
  is included in the final report; a successful outcome with such an omission is impossible.

## Plans and workflows

A plan item may run a workflow template in its stage (research, authoring, audit, development). The plan
itself is driven only by `scripts/plan.py` verbs (`next, start, log, finish, check, render`) - see
[Methodology](./methodology) and [Plan structure](./plan-structure); templates never write plan JSON by hand.

## Scout

An optional, opt-in context map (decision D3): a weak model of the current provider reads the deterministic
context pack and answers with at most 40 lines of `path[:symbol] — why` plus an `Unknowns:` block. It never
writes code or decisions, and the default start makes no model call.

- Enable: `plan.py start <plan> <items> --actor P/M/E --scout` once, or `plan.py set <plan> plan --json
  '{"settings": {"scout": "auto"}}'` for every start (`--no-scout` overrides). The provider is the one in `--actor`.
- Config (owner-editable): `configs/command-routing.json` → `orchestration.scout.<provider>` holds `model`, `effort`,
  `argv` (placeholders `{model}`, `{effort}`, `{cwd}`; the prompt goes through stdin) and `timeout_s`. The catalog
  rejects unknown keys, providers and placeholders. A provider without an entry is skipped; only `claude-code`
  has one (`claude -p --model haiku --tools ""`: no tools, so no writes).
  Add other providers only after checking their `--help` for a non-interactive, read-only mode that reads stdin.
- Result: `context/<item>.scout.md` (generated, gitignored) and section 13 "Scout map" of the pack. A timeout,
  a non-zero exit or an empty answer never blocks `start`: the pack is built without the map.
- Read the outcomes in `log.jsonl`: events of type `scout` with `data: {provider, model, outcome: ok|failed|skipped,
  seconds, lines}` (`plan.py stats` summarises them from P4.2).

## Bundles

- Review profiles for `wf-audit-adversarial.js` (constitution + measurements by type
  artifact) - skill `quality/artifact-review`; conformance-finder's by stack skills -
  command `/task:review`.
- Full cycle in which workflow templates occupy the research/exec/review stages -
  [Methodology](./methodology).
