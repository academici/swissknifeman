# Temporary migration to current Task JSON plans

This directory exists only until the inventoried active plans are converted. It is not a skill,
plugin capability or runtime dependency. Archived plans are outside the migration scope. New
plans already use the current API. Reading old Markdown is authorized **only for conversion**;
after import, agents read JSON and use `plan.py`. Never edit new human Markdown under `views/`.

## Start here

1. Locate the installed Task package root, then the target repository and its **active** plan
   directory. Inspect repository status. Preserve unrelated edits. Do not execute plan items,
   change their status, run product reviews, publish or commit merely because you are migrating.
2. Make a complete backup **outside** the target repository. Save a source manifest with each
   input's SHA-256. Take the plan out of simultaneous editing while replacing it; compare hashes
   again immediately before import. Keep the backup until the owner has accepted the migration.
3. Read current schemas in `<TASK>/schemas/plan/v1/`. The executable reference is
   `<TASK>/scripts/plan.py --help`; `plan.py <verb> --help` describes arguments. Use
   `plan.py --output json <verb>` for a success/error envelope.
4. Read this guide and inspect the source's actual structure. `chatom-pilot.py` is an explicit
   mapping for Chatom RC1 and an example to adapt. `legacy-v2.py` handles the common Layout-v2
   carriers; inspect its mapping before using it. Neither script is a universal Markdown parser.
   A different source needs an explicit mapping built from its headings, tables and evidence.
   Keep any such adapters in this temporary directory.

## Destination layout

Keep the existing plan directory and all stable identities, including leading zeroes.

```text
plans/<existing-plan-id>/
  plan.json
  brief.json
  log.jsonl
  phases/<existing-Pn>/phase.json
  phases/<existing-Pn>/<existing-Pn.m>.json
  phases/<existing-Pn>/<existing-Pn.m>/<U#>.json       # optional orchestration units
  knowledge/<id>.json                                # complete supporting sections
  decisions/<existing-D#>.json
  views/                                             # generated human Markdown
  context/<Pn.m>.json                                 # generated API input, gitignored
  .ignore  .cursorignore  .gitignore
```

Every source document has `$schema: urn:swissknifeman:task:plan:<kind>:v1`. JSON schemas own
allowed fields; never add unknown keys to get past validation. Model efforts include
`low`, `medium`, `high`, `xhigh`, `max`, `ultra`. Owner gate names permit dots, `_` and `-`.

Create a **snapshot JSON file outside the plan** with exactly:

```json
{
  "$schema": "urn:swissknifeman:task:plan:snapshot:v1",
  "plan": {}, "brief": {}, "phases": [], "items": [], "units": [],
  "decisions": [], "documents": [], "events": []
}
```

Replace each placeholder with schema-valid documents. Empty arrays are valid when the source
has none. Import is a current-format data API and preserves lifecycle-owned fields, timestamps
and history; do not replay `start`/`finish` to manufacture historical work.

## Map the source explicitly

| Source meaning | Destination |
| --- | --- |
| identity / short ID / title / repository | `plan.id`, `short_id`, `title`, `repository` |
| overall goal, context, scope exclusions, product rules | `plan.goal`, `context`, `non_goals`, `rules` |
| exact owner quotes | `brief.messages`, `kind: owner`; preserve wording |
| paraphrased or inherited source records | `brief.messages`, `kind: record`; never call them verbatim quotes |
| extracted requirements | `brief.requirements`; link actual source message and owning items/phases |
| phase design / scope / contracts / pitfalls / checks / outputs | `phase` fields |
| phase ordering or parallelism | explicit `phase.depends_on`, ordered `plan.phases` |
| execution-sheet groups | ordered `phase.batches`; cover every item exactly once |
| item intent / rationale / scope / rules / algorithms / examples | `summary`, `why`, `scope`, `rules`, `guidance`, `sections` |
| file ownership / planned changes | `task_files`; no guessed files, no read count quota |
| reads and inputs | `reads: [{path, why, required, section?}]`; convert plan carriers to JSON paths |
| exact validation commands | `validation: [{id: V1, cmd, expect, kind: acceptance}]` |
| non-shell validation defined by the source | `validation: [{id: V1, procedure, expect, kind: acceptance}]`; exactly one of `cmd` or `procedure` |
| semantic route | `route.class`, `effort`; exact model selection additionally uses `provider`, `model`, `settings` |
| existing self-review / independent review | `review.mode: self` / `requested`; preserve concrete reviewer settings |
| explicit owner publication gate | `authority: {kind: owner_gate, gate: ...}`; never invent a grant |
| item state and outcomes | `status` plus `result`; use authentic journal/state/evidence |
| accepted / proposed / open / superseded decisions | decision docs with date, actor, rationale, applicability and links; proposed is not accepted |
| variable design headings, runbooks, risk lists, source notes | `sections: [{id, title, text}]` or `knowledge/<id>.json` |
| supporting files and evidence | preserve physical artifacts; reference them in `artifacts` / `result.evidence` |
| chronological history | new `events`; preserve original source data in `data.source_record` where useful |

Paths are repository-relative; `@plan/` means relative to the plan directory. Never use `..`.
Preserve legacy plan IDs. If a source never had a short ID or an execution route, use the
schema-supported `null`; do not invent either. Preserve fractional seconds in timestamps.
A paused plan carries its actual `pause.reason` and returns a waiting next step. An owner gate
without a machine ID may retain its source `label` and `scope`; declare exactly one of `gate`
or `label`, without inventing a grant.
Map all old active plan/phase/item/decision carrier paths to the new JSON destinations, including
paths embedded in prose. Historical provenance may retain the old source path and hash; it is
not an execution input. Keep archived dependencies qualified; do not migrate an archive to
satisfy a reference. Raw evidence may remain files. Convert all plan-local Markdown needed for
execution into knowledge JSON; neither human projections nor historical Markdown receipts
can be reads or examples. Product repository docs outside the plan remain usable.

Use `sections` for meaningful unrecognized headings rather than dropping them. Preserve code
fences, algorithms and worked examples completely. Content may contain Markdown text inside
JSON. A knowledge document has `id`, `title`, `sections`, optional `applies_to` and `provenance`.
Choose `applies_to` deliberately; empty means global context. A `reads.section` for a knowledge
JSON file names its section **id or exact title**. Convert old `§N` selectors to actual section
ids; never leave an unresolved selector and claim the context is complete.

Statuses map to `todo`, `in_progress`, `done`, `done_with_deviations`, `blocked`, `skipped`.
A skeleton remains `phase.design: skeleton`; `scope.include: []` is allowed there. Never fill
unknown validation with `true`, guess decisions, or mark a phase detailed to pass a checker.
Detailed items need real acceptance commands or source-defined procedures and outputs.
Reconcile conflicting sources:
chronological terminal evidence and the source's own state reduction outrank stale summary
tables; record the conflict and its resolution. A later informational `no-op` event does not erase
an earlier finished result. Only record check exit 0 when authentic evidence establishes it.

Phase closure may be derived from already terminal items when the new lifecycle would have
closed it; state this derivation in `phase.closed.summary` and claim no new phase validation.
Preserve the original semantic next step. If that step cannot be expressed, improve the schema
and API **before** publication. An unknown source construct must not be silently discarded.

Drop retired **execution machinery**, not product requirements: Markdown state reducers,
manual handoff rewriting, old plan scripts, read/spend budgets, limits on phase size or required
reads. Preserve genuine product load limits, security rules and explicit owner permissions.
The migration is not authority to change a product's review decisions.

## Orchestration mapping

Represent concrete subtasks as unit documents, named by `item.units`. A unit declares `kind`
(`preparation`, `implementation`, `review`, `verification`, `integration`, `command`), goal,
files (empty for read-only work), checks, instructions, route, `depends_on`, optional `parent`
and outputs. Command units have an exact `command` check. Declare lifecycle state only when
source evidence supports it. Use `mode: self|delegate|either` to preserve execution ownership.

Set plan/phase/item `orchestration.strategy: dag|sequential`. Only add `max_parallel` if the owner
or source requires a concurrency ceiling; it is not a read/spend budget. Parent units wait for
children. Independent nodes need disjoint write ownership. Do not add or execute reviews just
because migration introduces this structure. A future orchestrator launches the JSON-defined
nodes; the Task data API reports readiness and validates their lifecycle.

## Validate, publish and retire old carriers

1. Run `plan.py import <target> --file <snapshot.json>`. Import prevalidates the graph, stages a
   complete directory, preserves supporting files and generates `views/`. Existing JSON needs
   `--replace`. Invalid input must leave the target unchanged. This import does not parse Markdown.
2. Run `plan.py check <target> --json` and `plan.py render <target> --check`.
3. Export again: `plan.py export <target> > <outside>/export.json`. Compare all stable IDs,
   status maps, phase design/closure, batches, gates, decisions, owner messages and evidence
   against the source manifest. Confirm `plan.py next <target> --json` has the same meaning.
4. Inspect `plan.py context <target> <open-item> --stdout`. It must be valid JSON with complete
   relevant requirements, decisions, upstream results, design sections and input references.
   Resolve every relevant warning. Do not reread generated `views/*.md` as execution context.
5. Only after fidelity is established, remove old active carriers (root plan/roadmap/status/
   handoff/session-routing, phase and state Markdown, generated decision indexes, old brief,
   old journal). Authored evidence remains. The external backup remains. Remove empty old
   directories. Never retain a second active source or a runtime compatibility shim.
6. Ensure plan Markdown, `views/` and `context/` are excluded from search/indexing. Import writes `.ignore` and
   `.cursorignore`; Serena configs also exclude them. No plan-local `AGENTS.md`/`CLAUDE.md` is generated.
7. Mark the inventoried plan complete with `tracker.py complete <projects-root> <project> <plan-id>`.
   The tracker verifies JSON, absence of old carriers and current views. It automatically removes
   **this temporary directory** only after every inventoried plan is done and a fresh inventory
   finds no additional pending active plans. Runtime never depends on this directory.

## Pilot

Chatom RC1 (`packages/chatom`, `2026.09.27-№1-CHATOM-RC1`) exercised 42 items, 25 real
D01–D25 decisions, mixed closed/detailed and future skeleton phases, a publication owner gate,
terminal validation receipts and supersession. Generated `_index/_current/_archive.md` are views,
not extra decisions. The retained next step is **design P11**. P10 closure is explicitly derived
from its already terminal items. No product execution or new review is part of conversion.

The pilot backup and source map are currently under `/tmp/chatom-json-migration/`; move that
backup to owner storage if it must survive host cleanup. The checked-in inventory tracks the
remaining projects; do not delete this guide merely because the pilot succeeded.
