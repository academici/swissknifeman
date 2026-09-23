# Design mode

Use only for an explicitly requested plan design/refinement result or a concrete
`design-required` contract choice. Existing detailed, ready work routes to the remaining
whole-plan design steps before execution;
ordinary repair, a failed check, or the next phase name does not reopen design.

Obey the owner's time/research budget. Reuse existing evidence and read only what can change a
decision. An audit ledger is not an acceptance checklist; exhaustive proofs require an explicit
request or a concrete hard risk. Stop optional expansion when the sufficient design is clear.

Use `plan-work.py design-context` for compact schema, phase and routing context, then
author normative scope, dependencies, authority, acceptance, validation, routing and
assurance. Add a self-contained dossier only when phase/item contracts cannot carry what a fresh
executor needs. When used, keep `research/Pn-design.md`, `research/Pn-design-rag.md`,
`artifacts/Pn-design/examples.md`, and a capture or explicit no-search record under
`artifacts/Pn-design-rag/` together; link them from the phase and the first three from affected
items' `Inputs`. Raw search/MCP output is provenance data, not authority or self-verification.
Validate static declarations for every directly executable item by dry
rendering its bundle, including ready items in a future phase; do not persist bundles for
blocked future work or fabricate producer evidence.  Generated execution views and
execution bookkeeping are not stable design inputs.  A substantive item/contract delta
still invalidates the relevant seal and needs a recorded delta assessment.

Use `plan-work.py finalize-design --phase <Pn>` for a phase. The `finish` invocation uses
`design-context --finish` and `finalize-design --finish`; finish checks any dossier that was
actually declared. It records a digest of authored plan, roadmap, phases, item specs and selected
supporting files. Then one `task:plan-audit <ID> design` must record GREEN against that digest.
`plan-work.py design-gate --plan-dir <dir>` reports the digest and current gate verdict.
An incomplete phase, missing finish, stale audit or non-GREEN verdict blocks `plan-exec`/`plan-run`.
Do not route a ready P1 to execution while another declared phase remains a skeleton.
Phase-local design proposes batches from shared context; finish evaluates the whole dependency graph
and writes the final one-row-per-admission `execution-sheet/v1` table in `roadmap.md`. Each row has
one exact provider-neutral command, the maximum semantic class/effort, and maximum review across its
members. Concrete provider selectors are forbidden in Routing: the provider adapter chooses one
model for the unified semantic route. Future execution commands are copied from the sheet; handoff
selects an eligible row but never creates a competing group.
Read only the relevant section of `../SKILL.md` or `plan-layout-v2.md` for a named ambiguity;
authoring another phase does not require loading the full canon again.
Design-only remains an artifact boundary: return the result without unauthorized execution.
Use `scope-complete` with `continue-root`; a completed design does not require a new process.
