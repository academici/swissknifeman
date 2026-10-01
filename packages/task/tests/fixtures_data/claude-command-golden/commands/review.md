---
disable-model-invocation: true
description: "Risk-scaled read-only review of code, docs or specs."
argument-hint: "[artifact: diff / branch / PR# / docs path]"
model: sonnet
effort: high
---
This is a read-only review of `$ARGUMENTS`. Do not modify files.

Identify the artifact and observable risk, then select depth:

- `quick`: docs, config, or a small local diff; one correctness pass plus applicable project rules.
- `standard`: an ordinary code diff; correctness, security, and performance in the affected slice, with
  relevant targeted checks.
- `adversarial`: security/auth, destructive migration, payments/accounting, concurrency/shared state,
  irreversible external effects, or public API/schema; test concrete failure scenarios and use one independent
  finder/verifier only when a separate perspective is justified.

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
