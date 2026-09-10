# P5 fleet preflight

**Item:** P5.1

**Observed:** 2026-08-15

## No-write identity checkpoint

Before the production `plan` invocation, the ephemeral registry resolved the exact sealed set
of 23 stable project IDs with no missing or extra ID. The canonical sorted identity map for all
13,421 rebound provider artifacts has digest
`sha256:50f81de8b88e871a1ccaa6b27eefa45b7e735ddeb5c0b74a75d8f5ab1b02532e`:
13,233 targets were observable and 188 were missing. The map contains only stable project/artifact
IDs and digests; absolute roots and target bytes are excluded.

The two atomic `plan` output paths were both absent at the checkpoint:

- `artifacts/P5/fleet-action-manifest.json`: missing
- `artifacts/P5/fleet-transaction-log.jsonl`: missing

`artifacts/P5/fleet-action-approval.md` was also absent. It is not a `plan` output and will be
materialized only as a pending Owner decision carrier after the exact manifest hash exists.

## Admission verdict

All 13,421 sealed classification rows currently carry `action=no-op` and `owner=unknown`:
13,319 are `ambiguous`, 102 are `broken-link`. D26/D28 therefore permit only
`no-op-unresolved`; no live drift may be promoted to `relink`, `refresh-managed`, or cleanup.
The frozen manifest records 12,443 exact preimages, 566 drifted preimages, 188 missing targets,
and 224 rows in one project whose repository no longer contains the sealed commit. Those rows
stay protected and unresolved; the production action set performs zero consumer/provider writes.

## Environment and worktree evidence

- Provider-attested route is `gpt-5.6-sol/high`, cwd/approval/sandbox/invocation exact; Task
  Contract returned `pre_mutation=allow` and `pre_final=allow`.
- Worktree-local `maind health --cwd --json` reports both provider trust rows green.
- `codex doctor --json` is functionally green but reports a non-blocking update-probe timeout.
- `harness doctor` reports the global Claude `run-report` hook files stale. The dry-run repair
  would mutate user-global Claude state, so P5.1 records the defect and does not claim hook
  integrity green or expand this consumer no-write item into an environment repair.
- Baseline plan lint has eight pre-existing errors (five P4 write-site-note omissions and three
  legacy handoff-field omissions) and zero errors newly introduced by the P5.1 candidate.
- Foreign changes exist in `packages/task`, generated bundle files, and `roadmap/`; P5.1 does
  not stage or rewrite them.

## Test carrier

The initial complete carrier was red only at restart transition handling. One grouped repair
added the recovered `applied` WAL event after a public-apply crash and corrected the
exact-preimage expectation to `rolled-back`. The targeted transaction recheck is green.

The continuation dispatch narrowed target-path privacy validation to absolute/escaping/root
leakage while retaining secret-value checks for evidence payloads. The exact benign
`.agents/plugins/bundles/architect/figma-mcp-core/snippets/tokens.json` regression is green.
The full stdlib carrier is green (11 tests); two production `plan` builds are byte-identical;
the exact no-write `check` returns `allow` with empty byte delta. The frozen manifest contains
13,421 `no-op-unresolved` rows across 23 protected projects and zero consumer writes. Its semantic
identity is `sha256:8c134c75214cff8dc4193f3b251e1afaf5c3041135a942976571068ad527bae4`;
the file identity is `sha256:85718d56e67e019ab60967ca29760809af24126564760a58238b53ad415c1995`.

## Owner gate

`task.plan_authority.authorize()` classified the immutable manifest freeze as
`approval_required`. DecisionRequest `P5.1-fleet-action-manifest-owner-approval` bound the exact
manifest and empty P5.2/P5.3/P5.4 action sets. The repository owner selected `approve`; D83 and
the frozen approval carrier record the response/action digest. The approval does not widen the
empty action sets, so no consumer or provider state may change in P5.2–P5.4.
