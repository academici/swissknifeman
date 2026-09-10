# Lean Task lifecycle overhead — 2026-09-10

## Owner outcome

The owner stops normal phase progression before P3. Existing P7.1 is to be redesigned and executed
next as the single priority fix. It must simplify the Task control loop using the cost observed in
the P2 audit; it must not create another multi-phase optimization programme.

## Measured repository baseline

- The five canonical plan commands plus `plan-protocol/SKILL.md` contain 1,888 lines and 176,325
  bytes before their provider projections. `plan-audit.md` alone contains 342 lines / 37,704 bytes.
- The P2 audit repeated focused suites (193, 206 and 119 tests), the full 991-test Task suite,
  provider projection checks, Skiller validation and the aggregate docs build.
- `packages/task/scripts/validate.sh` additionally inspected other active plans and stayed red on
  12 errors from `2026.08.02-PROVIDER-CONTRACT-LOCALE`; those failures were outside the P2 product
  delta but still consumed diagnosis and evidence work.
- The audit had to rebind three historical item terminal records and regenerate state, status,
  decisions and bundles even though the owner-visible product change was already committed.
- Mandatory audit-fixer behavior expanded an independent review into product implementation,
  documentation, CHANGELOG, generator and evidence-carrier work. This mixed reviewer and executor
  ownership and made the audit duration unbounded on the normal path.

The observed problem is therefore not merely model latency. Mandatory full-scope validation,
duplicated policy prose, cross-plan failure coupling, unconditional derived-carrier work, strict
two-commit bookkeeping, and audit-as-second-executor combined into the delay.

## External verification

Perplexity Web was queried on 2026-09-10 with two bounded web+academic searches, restricted in the
prompt to primary or authoritative sources.

1. Long-running coding-agent workflow: original Agentless research supports staged localization,
   repair and validation rather than broad repository mutation; Anthropic's engineering guidance
   recommends compact durable state and just-in-time context; OpenAI's SWE-bench discussion
   distinguishes issue-specific and regression evidence. These support narrow execution units,
   compact handoff, diagnostic retries and progressive validation.
   Sources: <https://arxiv.org/html/2407.01489v2>,
   <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>,
   <https://openai.com/index/introducing-swe-bench-verified/>. Confidence: medium-high; benchmark
   results are directional and must be validated on this repository.
2. Risk/change-impact testing: ISO/IEC/IEEE 29119-1:2022 frames risk-based testing as the basis for
   prioritization; Rothermel and Harrold formalize safe regression-test selection; NIST SSDF keeps
   explicit security verification for security-relevant changes. These support affected-scope
   validation with wider gates at real risk/release boundaries, not unconditional full replay.
   Sources: <https://www.iso.org/standard/81291.html>,
   <https://dl.acm.org/doi/10.1145/248233.248262>,
   <https://csrc.nist.gov/pubs/sp/800/218/final>. Confidence: high for the general testing policy;
   repository thresholds remain an internal measured decision.

## Design verdict for P7.1

P7.1 should become **Lean Task control loop consolidation** and execute before P3 through an
owner-directed priority branch. It should replace overlapping future machinery rather than layer a
new fast path beside it.

The implementation target is one normal-path lifecycle:

```text
load compact task contract → implement → focused affected validation →
one terminal update/handoff → widen only on a declared risk boundary
```

Required simplifications:

1. Make audit an evidence/delta review, not a second executor. Permit at most one bounded
   bookkeeping repair; product findings return one exact owning continuation. No automatic second
   audit and no full replay without a new material hypothesis.
2. Make validation change-impact based. Focused checks are the normal item gate; affected-package,
   integration and full-repository suites are selected only by declared risk or release boundary.
   A baseline-proved foreign failure remains visible but does not block an unrelated item.
3. Collapse repeated plan mechanics behind runtime owners. Command prompts reference the owner API
   instead of copying block-confirmation, routing, carrier and delivery algorithms verbatim.
4. Generate only carriers whose inputs changed, once at the terminal boundary. Do not regenerate
   decisions, closure, every bundle or all item states unconditionally.
5. Remove mandatory two-commit topology on the normal path. One scoped atomic commit is sufficient;
   a second bookkeeping commit is used only when work actually crosses a session/ownership boundary.
6. Persist one semantic Next. Provider-native launch output is rendered from it by the delivery
   tool rather than hand-maintained in several carriers and final prose.
7. Capture route/session evidence once at admission and reuse it unless the route actually changes.
   Overshoot is accepted; failure to prove a non-security optimization must not create a repair loop.
8. Keep hard widening/review gates for security/auth, destructive migrations, irreversible external
   actions, payments/accounting, concurrency/shared state, public API/schema compatibility, and
   low-confidence impact analysis.
9. Remove unconditional fresh-root boundaries after design/audit. Use a fresh root only for measured
   context budget, missing capability, owner pause, or genuinely independent review; preserve an
   explicit owner request for a fresh session.
10. Delete or supersede overlapping planned work in P3.3, P6.1–P6.4 and the old P7.1 contract. Do
    not add a new schema/carrier/reducer unless the same change removes more complexity than it adds.

## Acceptance budget

- The canonical five plan commands plus plan-protocol shrink by at least 40% from the measured
  176,325-byte baseline, with shared algorithms named once and enforced in runtime/tests.
- A low-risk one-item fixture closes with one focused validation, one carrier-generation pass, one
  commit and no independent audit/full-package/fleet validation.
- A changed security/public/migration fixture still widens deterministically and fails closed.
- A foreign-plan red baseline is reported as non-gating for an unrelated item and gating when the
  dependency/ownership graph intersects the change.
- An audit fixture performs zero product edits, zero full replay and zero second audit when prior
  evidence is fresh; one material-risk fixture selects exactly one widened review path.
- The end-to-end fixture reports executed commands, reused evidence and wall time so the lean path
  is demonstrably cheaper than the stored P2 audit baseline.

## Scope guard

Do not solve this by adding a `lean=true` parallel protocol, another policy schema, another audit
kind, more status values, or a second provider-specific command set. Simplification must delete,
centralize or demote existing mandatory work. Preserve append-only historical evidence and do not
touch unrelated roadmap worktree changes.

## Verification status

- RAG: Perplexity Web advanced search x2 (web+academic), 2026-09-10, OK.
- Unverified → repeat pass: exact 40% reduction feasibility is repository-specific and must be
  tested during P7.1 design/implementation; it is a budget target, not an external fact.
- Workarounds/[POSSIBLE-DEFECT]: none; a parallel lean mode is explicitly rejected.
