# JSON plan API and orchestration

JSON owns the complete plan contract and its execution state. Agents use the Python API,
`scripts/plan.py`, or JSON documents. Markdown is a template projection for people, lives
in `views/`, and never supplies execution state, agent instructions or indexed context.

## Implementation order

1. Replace Markdown context packs and worker briefs with deterministic JSON responses.
   Include full relevant contracts, requirements, decisions, upstream outcomes and friction.
   Remove read counts, inline limits, truncated lessons and mandatory phase size limits.
2. Extend work units into orchestration nodes: preparation, implementation, review,
   verification, integration and command steps; dependencies and optional nesting; explicit
   provider/model/effort/settings. Use one unit lifecycle and one dependency graph.
   Resolve scheduling policy from plan → phase → item. Python reports ready work; a future
   provider orchestrator launches it. Do not silently launch agents or commands.
3. Add schema-backed knowledge documents for variable design sections, runbooks, examples,
   risks and supporting evidence. Include selected sections in JSON context without reading
   human views. Keep references and content together during migration.
4. Add snapshot export/import and atomic authoring transactions. Validate the complete
   proposed graph before publication, preserve historical states without inventing successful
   checks or owner grants, and keep error responses machine-readable.
5. Deliver `skills/plan-protocol` inside the Task marketplace plugin alongside its API,
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
owner gates, decisions and open work. Run the Task suite and regenerate provider projections.
Separate reviewer work is deferred at the owner's request.
