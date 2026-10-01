# Owner waiver of a repeated whole-plan design audit

By default execution is gated per phase and needs no design audit. A plan that declares `**Design Audit:** required` still needs a completed finish and an audit GREEN for its current authored design fingerprint. When the owner explicitly waives the repeated audit, select one accepted decision in `plan.md`:

```markdown
**Design Audit Waiver:** D52
```

The selected `decisions/D52-*.md` owns exactly one `design-audit-waiver/v1` JSON block with these fields:

| Field | Contract |
| --- | --- |
| schema_version | `design-audit-waiver/v1` |
| plan_id | Exact plan directory name |
| decision_id | Selected D#; one accepted matching decision file |
| scope | `whole-plan-design-audit` only |
| design_fingerprint | Exact SHA-256 returned by `design_snapshot`; a matching finish must already exist |
| owner_provenance | Closed object: plan-local `path`, SHA-256 `sha256`, exact nonempty owner `message` found in that capture |
| reason | Nonempty explicit rationale |

This is owner authorization, not provider-route attestation or an audit verdict. Recording the message does not infer owner consent; use only the actual explicit owner instruction. The selected accepted decision and captured message are the plan's authority carriers, following its existing owner-decision convention.

The runtime reports `PLAN_DESIGN_AUDIT_WAIVED_BY_OWNER`, including `owner_decision`, without appending a fabricated audit-green event. Unknown fields, ambiguous decisions, foreign scope, invalid/mutated provenance and paths outside the plan fail closed. An unfinished design still fails. A material authored design change makes the waiver stale, even after another finish; updating its fingerprint needs a new explicit owner decision. A recorded non-GREEN audit for the current finished candidate is not hidden by the waiver.

The waiver concerns only the repeated whole-plan design audit. Item Validation, independent full-review, producer dependencies, execution Routing, phase checkpoints and terminal admission remain unchanged. Without explicit selection, the usual missing/stale audit behavior remains intact.
