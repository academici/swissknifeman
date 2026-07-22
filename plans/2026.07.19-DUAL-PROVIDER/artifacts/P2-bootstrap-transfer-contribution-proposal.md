# P2.6 core contribution proposal — D104 bootstrap-transfer admission

**Status:** Accepted — Approval Owner D104, 2026-07-22; exact additive D110 seal, 2026-07-22.

**Shared package:** repository-root `core` (stdlib-only)

## Rule-of-Three and alternatives

The live self-host preflight found one unmanaged P6 memory hook colliding with one P5 lifecycle
hook and a missing companion handler. This is not a reusable adoption policy: P5 and P6 are the
two consumers of one frozen D104 transaction, while `core` owns the already-shared artifact lock
and containment primitives. Keeping it in either consumer would reverse dependencies and make
the transfer differently safe in each path.

Rejected alternatives: implicit adoption, a global repair bypass, a provider-specific core branch,
and a second lock format. Each either weakens ownership conflict or creates a package dependency.

## Minimal additive API

`BootstrapTransferAdmission` is immutable and has exactly: `decision_id`,
`existing_target_path`, `existing_preimage_sha256`, `created_target_path`,
`existing_artifact_id`, `created_artifact_id`, and `require_absent_lock=True`.
`plan_bootstrap_transfer(root, expected, *, lock_bytes, admission) -> ArtifactPlan` is the only
new planner. It accepts exactly D104's two paths, IDs and preimage; it adds no target discovery,
environment input, provider branch, global state or lock schema.

`ChainedBootstrapTransferAdmission` is a second immutable, closed descriptor. It contains the
sealed `BootstrapTransferAdmission` predecessor plus exactly `decision_id = D108`, target
`.mcp.json`, preimage `sha256:cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`,
artifact ID `maind.provider-deploy.claude-code`, boundary `whole-file`, and ordered server IDs
`maind`, `perplexity-web`, `serena`. `plan_chained_bootstrap_transfer(root, expected, *,
lock_bytes, admission)` is its sole planner. It accepts only the sealed D104 two-artifact
predecessor plus that one unchanged MCP record, an absent canonical lock, and the exact
three-record final lock. It adds no target discovery, callback, wildcard, arbitrary hash list,
force/adopt flag, provider branch, global state or lock schema.

## SemVer and boundary

This is backward-compatible artifact-contract/core minor v1.3.0. Existing v1.0/v1.1 render,
lock, normal plan/apply/repair and `ownership-conflict` behavior are unchanged. The transfer is
not live authority: callers must supply the exact two native render results and an explicit root;
P2.6 tests use temporary roots only. P5.8 and P6.7 are the separately scoped native renderer and
deployment consumers.

The chained planner is likewise design/no-write only and is exercised only below
`TemporaryDirectory` in P2.7. Apply validates the complete three-target pre-state before its
first write, creates recoverable backups, leaves `.mcp.json` bytes unchanged, writes the
canonical lock last, and restores the byte-exact pre-state while removing only transaction-created
partials after any failure. Live apply/repair/rollback remains a separately gated P7.2 consumer
operation; P6.11 is the separately scoped disposable-root composition consumer.
