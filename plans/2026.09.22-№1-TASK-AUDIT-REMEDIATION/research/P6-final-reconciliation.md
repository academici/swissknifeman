# P6 final reconciliation

## Product result

The runtime repairs remain owned by P2–P5. P6 adds one consumer-facing layer: Task Contract
JSON now keeps exact internal diagnostics while exposing stable recovery categories:
`schema-invalid`, `evidence-missing`, `evidence-stale`, `evidence-forged`,
`policy-denied`, `conflict`, `corrupt-state`, and `durability-failed`.

The mapping is additive. Existing consumers may continue reading `pre_mutation`,
`pre_final` and process exit status. New consumers read `reason_codes.*.code`, retain
`internal_code` for diagnostics and must not parse the human message. An unknown internal
diagnostic fails safely as `policy-denied` rather than inventing a more specific recovery.

## Claim reconciliation

| Claims | Owning result | Public recovery outcome | Final status |
|:--|:--|:--|:--|
| N-01, N-02, N-04, N-05, N-13 | P2 false-green, context, batch, validation and CI repairs | blocked contract/context evidence becomes `evidence-missing`, `evidence-stale`, `evidence-forged`, `schema-invalid` or `policy-denied` while retaining the exact P2 code | repaired; P2 evidence reused |
| N-03, N-06, N-10, N-11, N-14 | P3 workflow-guard, activation-last, replay and observed-authority repairs | missing attestation is `evidence-missing`; forged binding is `evidence-forged`; denied authority is `policy-denied`; replay/activation collision is `conflict` | repaired with documented fail-closed provider limitation |
| N-07, N-12, N-15, N-16, N-17 | P4 typed exception, serialized journal, strict values/dates and durable projection repairs | malformed inputs are `schema-invalid`; corrupt history is `corrupt-state`; competing terminal state is `conflict`; failed persistence is `durability-failed` | repaired within the documented local POSIX boundary |
| N-08, N-09 | P5 policy-owned minimization and complete path classification/containment | malformed paths are `schema-invalid`; absent inputs are `evidence-missing`; policy/path escape is `policy-denied` | repaired; additive Task Contract path fields retained |

No claim was reopened by P6. The reason layer is a recovery projection, not a second
authority system and not a replacement for module diagnostics.

## Compatibility, rollback and release boundary

- Compatibility: `reason_codes` is additive; legacy JSON keys and full-gate exit semantics
  are unchanged. Consumers with a closed `additionalProperties: false` wrapper must admit
  the new field before upgrading.
- Rollback: remove the additive field/helper and documentation only. Do not collapse or
  weaken P2–P5 internal refusal codes.
- Release: CHANGELOG `[Unreleased]` records the public JSON addition. Tag, publish,
  marketplace release, consumer rollout and deployment remain separate owner actions.
- Prompt/provider projections: unchanged because no valid field comparison proved a
  behavioral benefit. Consequently no registry/provider regeneration is needed for P6.

## Field limitation

Corex, Agentools and Edufy all failed the frozen readiness gate before execution. This is an
honest `invalid comparison`, not a candidate regression or success. The exact predicates are
recorded in `findings/P6-field-results.md`. A future comparative run must first repin the task,
spec digest and predecessor/handoff state through a new protocol decision; P6 does not silently
rewrite the frozen sample.
