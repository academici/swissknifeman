<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/planner/commands/review.md
Canonical SHA-256: sha256:8de59557e90f6491267b6c32ed833eda2f70e6e28313dc7edbd069f0a0d6e72e
Adapter: planner.cursor-command/1.0.18
-->
---
disable-model-invocation: true
description: "Risk-scaled read-only review of code, docs or specs."
argument-hint: "<artifact: diff / branch / PR# / docs path> [--reviewer <provider/model>] [--effort high]"
---
Owner rules: run `python3 <Planner package root>/scripts/plan.py overlays planner:review` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
This is a read-only review of `$ARGUMENTS`. Do not modify files.

Read `references/reviewer-selection.md` for optional `--reviewer` and effort selection.
Without a selector, use the current native review route. A session that executed this candidate
must hand the review to a fresh read-only session; never review its own work as independent evidence.

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

For concurrency, transactions, auth or data integrity, use the shared invariant model as primary
context: affected operations/resources/drivers, enforcement and bypass paths, interfering pairs,
explicit and implicit lock order. Classify findings by risk class and stable subsystem/invariant.
A systemic re-review checks that model; local re-review checks findings and changed dependency closure.
For other risks, use the diff as primary context. Open manifests, local instructions, and skills only when they apply to the
changed stack or behavior. Do not scan the full registry, glossary, caller graph, or test suite for completeness.
Check adjacent rules in one pass and handle one or two applicable skills yourself. Verify changing external
premises against primary sources.

For each confirmed finding, report severity (`Blocker|Major|Minor|Nit`), confidence, `file:line`, the concrete
failure scenario, and its correctness, security, performance, or project-rule basis. Severity reflects impact,
not wording strength. Discard matches without reproducible impact. If there are no findings, say so and name
only material residual risk.

Run static analysis or tests only when they test a review hypothesis. Preserve the dirty baseline and route
fixes to the implementer.
