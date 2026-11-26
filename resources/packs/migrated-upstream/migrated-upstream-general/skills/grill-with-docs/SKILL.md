---
name: grill-with-docs
description: "Ruthless grilling session that SIMULTANEOUSLY builds a domain model: refines a plan/design one question at a time, cross-checking code AND external docs (API/RFC/banking specs), and writes the glossary (CONTEXT.md) and ADRs as it goes. Invoke EXPLICITLY to turn a vague idea into a strict spec with fixed terminology."
---

# Grill with Docs

Grilling = relentless clarification on one issue until the requirement becomes
strict. This skill combines grilling (`spec-interview`) with **active construction of domain
models** (`domain-modeling`): while you pull out the requirements - at the same time you fix the terms and
solutions. Difference from `spec-interview`: he grills the code + user; here a reconciliation with
**external documentation** and glossary entry/ADR inline.

## When to activate

Only **explicit call** (`disable-model-invocation: true`). Triggered when:
- the idea is vague and the cost of error is high (fintech integration, fiscal document flow);
- terms are overloaded and confused between sessions («operation» / «payment» / «translation» — for everyone
  banking API its meaning);
- requirement must be checked with external spec (SBP, SberBusiness, OFD, libfptr10).

For an obvious single-file fix - overhead, do not run.

## Algorithm

1. **Grilling by the rules `spec-interview`** — one question → recommended answer with rationale →
   branching. Passage categories: target → boundaries → invariants → edge cases → data → verification.
   Cannot be accessed «like», not closed yet «what» and «where».
2. **Sources first, user second.** We are looking for the answer in order: (a) codebase, (b) **external
   documentation** (official API-docks, RFC, protocol specs), (in) only then we ask the person.
   Quote source: «according to the SBP spec field X mandatory - can you confirm?».
3. **Active domain model in parallel** (`domain-modeling`): when overloaded/fuzzy term -
   stop and qualify canonical name; stress test the boundaries of concepts with a scenario; having found
   discrepancy «code ↔ user words ↔ spec» — open it immediately.
4. **Write online, not in batches.** Resolved term → immediately in `CONTEXT.md` (glossary only, without
   implementation details). Hard-to-reversible solution with real trade-off → suggest ADR (sparingly: only
   if «difficult to rollback» AND «surprises without context» AND «was a choice»).
5. **Summary** — completed technical specifications for `task-brief-template` (with «Explicit assumptions / Out of Scope /
   Definition of Done») + updated `CONTEXT.md`/ADR. Next - `to-issues`.

## Anti-patterns

- Ask what is in the code or in the official doc.
- A list of ten questions instead of one at a time.
- Put implementation details into `CONTEXT.md` (there is only the domain language).
- Produce ADR for each solution (only difficult-to-reversible with trade-off).

## Related skills

- `spec-interview` (general) — basic grilling rules (this skill is its extension for docks + domain).
- `domain-modeling` (architect) — format `CONTEXT.md` and ADR (snippets), active model discipline.
- `task-brief-template` (general) — where the total goes.
- `to-issues` (oss-dev) — next step: break the finished technical specification into vertical sections -issue.
