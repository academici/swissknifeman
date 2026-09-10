---
item: P7.1
date: 2026-08-16
gate: return-loop-v1
fingerprint_digest: 6595ab60c96f65a5eb3a289b664f02ab70084e1b642a2ed7a47926fcf22ecfd5
occurrences: 1
qualification: new
---

# P7 provider acceptance — P5 producer admission

**Observed:** 2026-08-16

P7.1 initially treated the zero-record P5 transaction journal as an absent producer. That was
incorrect. The P5 phase handoff and D83 define three empty action sets: all 13,421 rows are
`no-op-unresolved`, no consumer/provider write is authorized, and the durable WAL is therefore
correctly empty.

- `artifacts/P5/fleet-transaction-log.jsonl` has zero records by design;
- `artifacts/P5/P5.4-results.json` reports `journal_events: 0`, zero project outcomes, and
  13,421 `no-op-unresolved` action IDs, consistent with the frozen P5 result.

The frozen `verify-results --all-action-sets` carrier is the authoritative proof that this empty
WAL, action manifest, results, and convergence report form a complete P5 producer. P7.1 may
continue only after that exact verifier succeeds; it must still preserve the non-green rollout
state and must not turn the no-write result into a fleet-health or release-green claim.

## P7.1 replay admission — frozen selection is absent

**Observed:** 2026-08-16

This is independent of the corrected P5 admission. The frozen `skill-evidence-v1` contract
requires live positive, negative, and boundary workflows for every *migrated capability*, while
the P7.1 refinement says *sampled capability*. Neither freezes the selection or maps the P4.3
migration rows to capability IDs, workflow fixtures, stable graders, and retained non-core
instructions:

- `configs/locale-corpus-v1.json` and the accepted P4.3 checkpoint name exactly three migrated
  `semantic.skill` rows: `skill.repository-bootstrap.skill-authoring`,
  `skill.repository-bootstrap.package-architecture`, and
  `skill.repository-bootstrap.field-feedback-loop`;
- the only P2 skill-evidence fixture is explicitly `structure-only` and names the unrelated
  example capability `verify-external-claims`; its evidence references and ablation are
  `pending:P7`;
- no sealed producer declares which capability IDs P7.1 must sample, nor a real-project
  workflow/grader specification for the three migrated rows.

Consequently, choosing IDs or prompts in P7.1 would create new acceptance semantics and could
make a synthetic fixture appear to prove live efficacy. This is the P7.1 Code Guidance trigger
for `task:plan-design`, not a reason to reopen P2, P4, P5, or P6. The design successor must add
one explicit, frozen P7.1 replay-admission carrier (selection, exact P4.3 source anchors,
positive/negative/boundary fixtures, grader contract, per-provider adapter variants, and
non-core ablation inventory), then route back to P7.1. It must preserve the approved P5 no-op
producer and P7's no-mutation boundary.

**Evidence commands:**

```bash
wc -l plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/fleet-transaction-log.jsonl
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path('plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P5/P5.4-results.json').read_text())
print(data['journal_events'], len(data['project_outcomes']), len(data['unresolved_action_ids']))
PY
```

## P7.1 real replay and release composition remain non-green

**Observed:** 2026-08-16

The D87 admission source gate passed and the runner produced all 54 required base rows without
persisting provider bodies. Claude Code returned a provider-level 403 (`subscription access`
disabled) for all 27 rows. Codex completed all 27 rows, with 17 passing structured graders and
10 failing them. The finite declared ablation inventory has no evidence yet. The P5 aggregate
verifier passed, but the frozen P6.3 verdict still carries 24 required-project release blockers
and one required unavailable/cleanup axis.

The resulting P7.1 evidence bundle is privacy-minimized and self-verifying, but its blocker set
is non-empty. This is an admission result, not permission to infer peer success, waive Claude,
or relabel P6 as release-ready. Restoring Claude access and authorizing any exception to the
frozen P6 release gate require the relevant external/Owner authority; P7.1 remains in progress.

```json
{"boundary_evidence":["evidence:skill-replay-results:claude-code-27-of-27-unavailable","evidence:fleet-health-verdict:required-project-release-blockers-24","spec:P7.1-scope-excludes-live-repair-and-release-exception"],"evidence_ids":["evidence:skill-replay-results.json","evidence:acceptance-results.json","evidence:fleet-health-verdict.json","validation:p5-verify-results:green"],"executor_actor":"gpt-5.6-terra/high","external":false,"item_id":"P7.1","plan_id":"2026.08.02-PROVIDER-CONTRACT-LOCALE","rag":{"evidence_ids":[],"required":false,"status":"not-required"},"resolutions_tried":["D87 exact 54-row real replay","P5 aggregate verification","one bounded replay-runner repair","P7.1 scope review"],"review":null,"schema_version":"block-candidate/v1","scope_class":"authority","scope_coverage":"outside-scope","signal_class":"authority-boundary"}
```

Independent `isolated-child-return` review by `p71_block_review` returned `JUSTIFIED` against
`skill-replay-results.json`, `acceptance-results.json`, `release-blockers.json`,
`fleet-health-verdict.json`, and the P7.1 scope boundary.

## Owner package-boundary disposition (D88)

D88 keeps the exact matrix and fleet evidence but changes neither into a fabricated success: Claude
is documented `not-live-verified`; Codex and ablation output are diagnostic; and P5/P6 rollout
state is deferred external operational work. The regenerated acceptance bundle has zero **package**
blockers while retaining all of those deferred facts verbatim. P7.1 may therefore close with
deviations; it does not authorize a fleet rollout, tag, publish, or claim live provider efficacy.
