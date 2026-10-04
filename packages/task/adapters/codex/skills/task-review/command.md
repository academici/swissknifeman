<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/review.md
Canonical SHA-256: sha256:6a7053663d9a111f9d95ddfd5a6e6ec8897b3643f62d95b9734e0c8f03fec9d5
Adapter: task.codex-command/1.0.18
-->
This is a read-only review of `$ARGUMENTS`. Do not modify files.

Require explicit `--reviewer <provider>/<exact-model-id>`; accept `claude-code`, `codex`,
`cursor`, or `grok`. `--effort` defaults to `high`. This selects the reviewer, not the executor.
The selector also accepts optional context/effort suffixes and a trailing `/`: `grok/grok-4.7/500k/`,
`grok/grok-4.7/high/`, `grok/grok-4.7/hight/`, `grok/grok-4.7/500k/high/`.
Use `task.review_packet.invocation_selection`; context is required capacity, not a token-spend cap.
A suffix sets effort; a conflicting explicit flag fails closed. Only provider evidence proves context.
Capture the actual provider route and require the chosen model/effort in a fresh non-executor
session. A declared routing minimum is not evidence that the chosen reviewer ran.
These review commands do not pin a default model in native frontmatter. If the current route
differs, return the exact selected review launch; never silently substitute
the default model or let the executor impersonate a reviewer.
For a prepared item packet, read
`runtime/plan-protocol/references/review-mode.md` and use `plan-work.py review-run` for one Grok
transport attempt, or `review-record` from the independently routed session. Review ends with its
verdict and owning continuation. Never repair product or recursively launch a re-review.

Identify the artifact and observable risk, then select depth:

- `quick`: docs, config, or a small local diff; one correctness pass plus applicable project rules.
- `standard`: an ordinary code diff; correctness, security, and performance in the affected slice, with
  relevant targeted checks.
- `adversarial`: security/auth, destructive migration, payments/accounting, concurrency/shared state,
  irreversible external effects, or public API/schema; test concrete failure scenarios and use one independent
  finder/verifier only when a separate perspective is justified.

Use the invariant model as primary context for systemic risks (concurrency, transactions, auth,
data integrity); otherwise use the diff. Check affected operations, resources and drivers together,
including pairwise lock-order cycles and residual invariant races. Classify each finding by
`risk_class` and stable `area` (subsystem/invariant). A systemic re-review covers the affected
class/model; a local re-review checks findings and their changed dependency closure.
Open manifests, local instructions, and skills only when they apply to the
changed stack or behavior. Do not scan the full registry, glossary, caller graph, or test suite for completeness.
Check adjacent rules in one pass and handle one or two applicable skills yourself. Verify changing external
premises against primary sources.

For each confirmed finding, report severity (`Blocker|Major|Minor|Nit`), confidence, `file:line`, the concrete
failure scenario, and its correctness, security, performance, or project-rule basis. Severity reflects impact,
not wording strength. Discard matches without reproducible impact. If there are no findings, say so and name
only material residual risk.

Run static analysis or tests only when they test a review hypothesis. Preserve the dirty baseline and route
fixes to the implementer.
