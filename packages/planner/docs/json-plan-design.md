# JSON plan API and orchestration

JSON owns the complete plan contract and its execution state. Agents read and change plan data
only through `scripts/plan.py`; they never open or edit plan source files directly.
Markdown is a template projection for people, lives
in `views/`, and never supplies execution state, agent instructions or indexed context.

## Read API

Use `python3 <Planner package root>/scripts/plan.py`. Pass a plan directory id, Short ID (`PLAN<N>`)
or path as `PLAN`. Repository code and documentation remain ordinary readable files.

| Need | Command after `plan.py` |
| --- | --- |
| Complete document or selected knowledge section/fields | `get PLAN REF [--section ID] [--fields a,b]` |
| Filtered document rows | `list PLAN item\|phase\|decision\|document\|unit [--status S] [--phase Pn] [--applies-to REF]` |
| Incoming/outgoing typed graph | `links PLAN REF [--direction out\|in\|both] [--kind K,...] [--depth N]` |
| Item, graph, decisions and knowledge together | `neighborhood PLAN ITEM` |
| Journal events | `events PLAN [--item REF] [--type T,...] [--since TS] [--limit N]` |
| Declared artifact metadata, digest and optional complete content | `artifact PLAN artifact/ID [--inline]` |
| Live parser-derived verb catalog or complete schema | `schema --verbs` or `schema KIND` (no plan needed) |

These queries return one validated envelope: `{"ok": true, "data": ...}` or
`{"ok": false, "error": {"code": "REF_UNKNOWN", "message": "..."}}`.
Exit codes are 0 for success, 1 for refusal and 2 for usage. They take no plan lock and write no
files. Data is complete unless the caller explicitly selects fields, sections, filters, graph
depth or event count. The catalog names arguments, modes, refusal codes and dedicated `read-*`
data schemas; `schema KIND` retrieves the schema, including definitions.

Typed references include `Pn`, `Pn.m`, `Pn.m/U#`, `D#`, `knowledge/<id>[#section]` and
`artifact/<id>`. Qualify them as `PLAN<N>.<ref>` or `<repo>:PLAN<N>.<ref>`; `plan` and `brief`
are whole-document query selectors. `get`/`artifact` can resolve another plan, with repeatable
`--repo NAME=PATH` or `SKM_PLAN_REPOS` for another repository. Graph queries do not load foreign
plans: those nodes keep their qualified ref and null metadata. Incoming edges retain their
original `from`/`to`; default direction is `both`, default depth is 1, and cycles terminate.

`show PLAN REF` preserves its document-only output; `show PLAN` preserves the overview.
`context PLAN ITEM --stdout` keeps the full execution pack. Existing verbs support the same envelope with the global
`--output json` option before the verb.
Bridges: `plan.py bridge list`; a bridge projects plan data for an external executor (see the bridge's README).

## Validated links and artifacts

All typed links share the `defs.ref` grammar and one edge-field table. Optional `reads[].ref`
names local plan data in place of `path`; exactly one is required. Select a knowledge section
with either `#section` or the separate `section` key. Optional artifact ids identify
unique output declarations, and input artifacts cite the matching output id/path. Existing
path-based reads and artifacts stay valid without migration. `check` validates target kinds,
local resolution (including knowledge sections), cycles and supersession backlinks; reverse
edges are computed rather than stored.

Use `link PLAN SOURCE TARGET --kind KIND` and `unlink PLAN SOURCE TARGET --kind KIND` for local
`depends_on`, `related`, `decision`, `applies_to` or `unit_depends_on` links. Related links need
`--relation informs|consumes|conflicts|follows_up|supersedes` and optionally accept `--note TEXT`.
Qualified refs require the schema-supported `set`/`apply` authoring path. Declare artifact
metadata with `add-artifact PLAN ITEM --path PATH --role input|output [--id ID]`; it does not
create the file. Each mutation holds a lock and validates the document and proposed graph
before publication. Refusals leave source documents and events unchanged; exact repeats are
no-ops and report `changed: false`. Lifecycle state stays owned by lifecycle verbs.

For complete result shapes, writable source/target pairs, id rules and errors, read
`skills/plan-protocol/references/api.md` in the planner package. The live catalog and schemas
are available without reading plan files.

## Implementation order

1. Replace Markdown context packs and worker briefs with deterministic JSON responses.
   Include full relevant contracts, requirements, decisions, upstream outcomes and friction.
   Remove read counts, inline limits, truncated lessons and mandatory phase size limits.
2. Extend work units into orchestration nodes: preparation, implementation, review,
   verification, integration and command steps; dependencies and optional nesting; explicit
   provider/model/effort/settings. Use one unit lifecycle and one dependency graph.
   Resolve scheduling policy from plan → phase → item. Python reports ready work; a future
   provider orchestrator launches it. Do not silently launch agents or commands.
   Scope content to packs by `applies_to`/`global`; `check` warns on `context_unbound`,
   `brief_duplicate`, `context_heavy` and `context_legacy`, and `design-done` prints a pack size report.
3. Add schema-backed knowledge documents for variable design sections, runbooks, examples,
   risks and supporting evidence. Include selected sections in JSON context without reading
   human views. Keep references and content together during migration.
4. Add snapshot export/import and atomic authoring transactions. Validate the complete
   proposed graph before publication, preserve historical states without inventing successful
   checks or owner grants, and keep error responses machine-readable.
5. Deliver `skills/plan-protocol` inside the planner marketplace plugin alongside its API,
   templates and schemas. A second separately versioned plugin would split one contract.
   Commands activate the installed skill only when explicitly invoked.
6. Convert Chatom's active RC1 plan while writing a temporary migration runbook. Real source
   cases drive schema corrections. Archived plans stay untouched. Migration code and tracking
   live only under `docs/migration/`, outside runtime; remove that directory when the migration
   inventory is exhausted. New plans always use the current JSON format.

## Contract choices

- Stable item/unit identities survive migration, including leading zeroes.
- Model class is a minimum capability hint; an explicit provider/model pins the selected route.
  Provider settings are JSON values passed by the future orchestrator, never shell fragments.
- Units may be read-only. Review steps own no product files and declare evidence/outputs.
  Child units finish before their parent. Sequential scheduling adds ordering; DAG scheduling
  uses explicit dependencies and disjoint write ownership. No global reading or spending quota.
- Plan checks validate JSON only. Human view staleness is checked explicitly by `render --check`;
  deleting a view must never prevent execution.
- Snapshot import is a general data API, not a legacy Markdown parser. Conversion is a temporary
  owner-authorized task that constructs current schema documents and tests semantic fidelity.
- Optional source provenance belongs in JSON. Old carriers cease to be active sources after
  conversion. Preserve reversible backup outside the active plan before replacement.

## Verification

Exercise JSON context, generated-view isolation, snapshot round trips and failed-import
rollback, graph validation, route selection and full unit completion. Verify the Chatom
conversion by matching source identities, states, detailed contracts, execution order,
owner gates, decisions and open work. Run the planner suite and regenerate provider projections.
Separate reviewer work is deferred at the owner's request.
