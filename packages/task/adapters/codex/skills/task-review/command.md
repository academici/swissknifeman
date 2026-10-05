<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/review.md
Canonical SHA-256: sha256:781c008bbde8a4cb0185fc94fb33e05c44f87be3a5f8b9becacf7648eb5ea48b
Adapter: task.codex-command/1.0.17
-->
This is a read-only review of `$ARGUMENTS`. Do not modify files.

Identify the artifact and observable risk, then select depth:

- `quick`: docs, config, or a small local diff; one correctness pass plus applicable project rules.
- `standard`: an ordinary code diff; correctness, security, and performance in the affected slice, with
  relevant targeted checks.
- `adversarial`: security/auth, destructive migration, payments/accounting, concurrency/shared state,
  irreversible external effects, or public API/schema; test concrete failure scenarios yourself.

This is one reviewer making one pass over the whole artifact, in this session. Do not split the review
into per-file or per-slice partial passes and do not spawn subagents; use one independent verifier over
the complete finding list only when the owner explicitly asked for an independent or second-opinion
review. Report and stop: no self-started fixes and no repeat review. A re-review on request covers only
the earlier findings and the code that fixed them.

Use the diff as primary context. Open manifests, local instructions, and skills only when they apply to the
changed stack or behavior. Do not scan the full registry, glossary, caller graph, or test suite for completeness.
Check adjacent rules in one pass and handle one or two applicable skills yourself. Verify changing external
premises against primary sources.

For each confirmed finding, report severity (`Blocker|Major|Minor|Nit`), confidence, `file:line`, the concrete
failure scenario, and its correctness, security, performance, or project-rule basis. Severity reflects impact,
not wording strength. Discard matches without reproducible impact. If there are no findings, say so and name
only material residual risk.

Run static analysis or tests only when they test a review hypothesis. Preserve the dirty baseline and route
fixes to the implementer.
