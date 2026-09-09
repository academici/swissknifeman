# Repeat whole-plan design-audit root cause — 2026-09-09

## Observed recurrence

The first durable whole-plan design audit ended ATTENTION and named F1–F4. The bounded design root
repaired those four findings, regenerated the owned views/bundle and produced green scoped lint.
It nevertheless persisted another `audit-design` as Next.

## Why it happened

1. `packages/task/commands/plan-design.md` hardcodes the successful `finish` successor to a fresh
   whole-plan design audit.
2. The Task Development Philosophy separately requires evidence reuse and rejects repeated audits
   without a new material hypothesis, but no deterministic whole-plan design-completion reducer
   reconciles those rules.
3. The handoff/lint/delivery path can represent either `audit-design` or `run-items`, but it does not
   own a policy test proving when repaired ATTENTION may use the latter.
4. In that ambiguity, the design root optimized for the literal command checklist and treated the
   remediation's carrier delta as sufficient reason to replay the audit. That was the wrong
   decision: the delta consisted of the requested bounded plan repairs, not a new unresolved risk.
5. The owner had already required the next command to be grouped execution. I failed to apply that
   instruction as the controlling continuation decision and left it only as a dormant successor.

The recurrence is therefore a command/policy ownership defect plus an execution judgment error,
not missing information from the owner.

## Immediate correction

D13 accepts the bounded residual design-review risk without fabricating a GREEN verdict. The current
handoff is P1.1–P1.3 as one B-P1-ECONOMY `plan-run` batch. No second design audit is scheduled.

## Permanent correction

P7.1 owns one vertical Task change: a deterministic whole-plan design-completion continuation used
by `plan-design`, design-audit handoff, lint and delivery. Bounded resolved remediation and audit
bookkeeping cannot select another audit by themselves. A new audit requires an unresolved material
boundary, a concrete new broad hypothesis, or an explicit owner request. The regression fixture is
this exact ATTENTION→F1–F4 remediation→grouped execution lineage.

## Integrity boundary

No historical journal event or verdict is rewritten. The durable audit remains ATTENTION attempt 1.
No product item, status, immutable `artifacts/source-roadmap/` byte, release or external action is
changed by this design correction.
