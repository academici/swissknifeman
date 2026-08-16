# P6 required/optional project membership design

## Inputs and authority

This synthesis consumes
`findings/29-p6-optional-membership-design-preflight-2026-08-16.md`,
`findings/P6.3-brain-optionality-authority-boundary.md`, the accepted owner response for
`DR-P6-BRAIN-OPTIONALITY-1`, D32, the frozen `provider-health-v1` contract, P6.1's sealed target
identity and the current P6.3 exporter/evidence bundle. It introduces no external fact.

The owner chose a provider-neutral required/optional membership contract: Brain is an optional
integration, its absence cannot gate package runtime or fleet release, and neither schema nor code
may special-case the Brain name. D32 continues to own exact evidence coverage for every sealed P0
project; the owner response changes only which project outcomes participate in release admission.

## Target boundary

Health evidence and release admission become two explicit, non-interchangeable results:

1. `provider-health-v1` keeps its current exact sealed-set aggregate. Every missing, unavailable,
   stale or non-green optional project remains present and may keep the health aggregate
   `non-green`. No P6.2 package runtime, public mAInd evidence-set schema or evaluator result shape
   changes.
2. P6.3 produces a sealed `provider-health-release-membership/v1` instance with exactly one row
   for every sealed P0 project ID. Each row declares `required` or `optional`, its authority source
   and stable provenance; missing, extra, duplicate, unknown or unproven rows refuse before a
   release verdict.
3. The current instance derives the optional stable project ID from P6.1's
   `sealed_project_id` and binds it to the exact owner response/action digest. All other sealed IDs
   are explicit `required` rows under D32. The exporter consumes IDs and authority carriers; it
   contains neither a project-name branch nor a literal stable-ID exception.
4. P6.3 keeps optional non-green/unavailable rows in project health and an
   `optional_non_green` section, but excludes them from project-scoped release blockers. Required
   non-green/unavailable rows remain release blockers. Cross-fleet blockers such as unauthorized P5
   rollout, membership/source drift, malformed evidence, privacy failure or semantic mismatch
   remain release-gating regardless of membership.

The membership schema is an adjacent plan-local contract,
`root/contracts/provider-health-release-membership-v1.schema.json`. Its runtime instance lives in
the P6.3 minimized evidence bundle as `project-membership.json`. This avoids modifying the already
green P6.2 package runtime and gives P7 a deterministic, digest-bound admission input.

## Compatibility and validation economy

The existing `provider-health-v1` and
`provider-health-evidence-set-v1.schema.json` bytes remain frozen. P6.3 changes only its plan-local
schema, exporter, minimized evidence, finding and bundle verifier. Existing P6.1/P6.2 product-suite
receipts remain reusable because their inputs and outputs do not change. The reopened P6.3 runs
one changed-item validation pass; only a reproduced failure permits one grouped repair and one
targeted recheck. The previous full P6 audit remains the material baseline, so closure needs a
delta/gate rebind over D86 and the rebound P6.3 evidence, not another full audit absent broader
material change.

## Alternatives

| Alternative | Disposition | Reason |
|:--|:--|:--|
| Remove optional projects from the sealed P0 set | Rejected | It would violate the brief and D32 exact evidence coverage and hide optional integration health. |
| Make the health aggregate ignore optional projects | Rejected | It would conflate health with release admission and require a broader P6.2 runtime/contract change. |
| Special-case `brain` or its current stable ID in the exporter | Rejected | It violates the owner decision and is not reusable for another optional integration. |
| Explicit exact-set membership carrier plus separate release verdict | Accepted | It is deterministic, provider-neutral, privacy-minimized and local to the proven P6.3 defect. |

## Failure conditions

- If the public mAInd input/result shape must change, stop: that crosses the declared P6.3 local
  repair and requires P6.2/package redesign.
- If the exact owner response, D86 semantics, P6.1 sealed project identity or P0 project set cannot
  be rebound, refuse before live probes; do not infer membership from a name, path, live registry
  or observed health.
- If optionality removes a global blocker or suppresses evidence rather than only a project-scoped
  release blocker, Validation must fail.

## Verification

- RAG:— (repo-grounded: the findings and carriers named above).
- No `[NEEDS CLARIFICATION]` remains; the owner selected the only material product choice.
