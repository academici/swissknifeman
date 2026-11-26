---
name: spec-interview
bucket: general
version: 0.2.0
description: "Pre-code interview: one question at a time, reads the codebase itself, proposes a recommended answer."
when_to_use: "Use when starting an ambiguous task before writing code."
model: sonnet
effort: medium
risk: draft
persona: oss-dev
tags: [workflow, requirements, discovery]
requires: []
produces_for: [task-brief-template]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Spec Interview

## When to activate

- User arrives with a fuzzy idea ("add export", "make it faster"), not a finished spec.
- Skip for trivial tasks (obvious single-file fix) — interview is overhead.
- Need to also check external docs (API/RFC/bank specs) and capture a domain glossary/ADR in parallel → use extension `grill-with-docs` (grilling + `domain-modeling`).

## Interview rules

1. **One question at a time.** Not a list of ten — question → answer → next question. Branch on the answer.
2. **Codebase before user.** If the answer is findable by reading code (validation already exists, pattern in use, where a similar feature lives) — agent reads it, doesn't ask.
3. **Recommended answer per question.** Agent proposes its option with a short rationale; user says "yes" or corrects.
4. **Question dependencies.** Don't move to "how" (implementation) until "what" (behavior) and "where" (boundaries) are closed.

## Question categories (pass order)

| # | Category | What to determine |
|---|---|---|
| 1 | Goal | Result needed by user/business, how we know it's done |
| 2 | Boundaries | What's in, what's explicitly NOT in, which files/modules may be touched |
| 3 | Invariants | Which contracts, formats, behavior must not break |
| 4 | Edge cases | Empty data, concurrent access, external-system errors |
| 5 | Data | Where sourced, where written, migrations, volumes |
| 6 | Verification | Which tests/checks confirm the result |

## Output

- All accepted decisions → filled `task-brief-template` (incl. sections "Explicit Assumptions", "Out of Scope", "Definition of Done").
- Unresolved items → recorded as explicit assumptions, not silently dropped.

## Anti-patterns

- Asking a question whose answer is in the codebase.
- Asking everything as a list — user answers half.
- Starting implementation before categories 1–3 are closed.

## Related skills

- `task-brief-template` (general) — interview output lands in this spec template.
- `grill-with-docs` (general) — same interview + external-doc cross-check + inline domain glossary/ADR.
- `complex-task-orchestrator` (general) — after the spec is fixed, decompose a complex task.
- `to-issues` (oss-dev) — split a finished spec into independent issues by vertical slices.
- `implement` (general) — implement per fixed spec/issue (explicit invocation).
- `pm/requirement-critic` — audit a larger BRD for completeness and conflicts (different scale: product requirements, not a one-off task).
