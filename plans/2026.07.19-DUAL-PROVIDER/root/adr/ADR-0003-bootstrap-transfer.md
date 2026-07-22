# ADR-0003 — closed D104 bootstrap-transfer admission

**Status:** Accepted — Approval Owner D104; exact additive D110 seal

## Context

The normal P2 engine correctly refuses an unmanaged `.codex/hooks.json`. The owner approved one
exact bootstrap preimage only after the P7.2 no-write preflight proved that normal repair cannot
create the paired lifecycle handler safely.

## Decision

Add a v1.2.0 closed `core.provider_lock` admission with an immutable descriptor and one planner.
It verifies the exact D104 decision, SHA-256 preimage, two project-relative targets, two artifact
IDs and absent lock before every transaction write. It writes a recoverable first-target backup,
the two targets, then one canonical lock. Failure rolls back only exact transaction-created state.

D110 adds one v1.3.0 composition, not a second adoption path: an immutable
`ChainedBootstrapTransferAdmission` embeds the sealed D104 predecessor and admits exactly one
whole-file `.mcp.json` record, `maind.provider-deploy.claude-code`, only for preimage
`sha256:cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283` whose expected JSON has
the exact server-ID set `maind`, `perplexity-web`, `serena`. Its sole planner,
`plan_chained_bootstrap_transfer`, preflights the D104 pair, MCP record, absent canonical lock,
exact backup destinations and the canonical three-record final lock before the first write.
It leaves MCP bytes unchanged, writes recoverable backups and the lock last, and on failure
restores byte-exact pre-state while removing only transaction-created partials.

## Consequences

Ordinary create/update/repair and every non-D104 ownership conflict remain fail-closed. No second
lock format, discovery, provider branch, wildcard/hash-list adoption primitive or live-root
operation is introduced. P5.8 supplies native Codex composition; P6.7 supplies the caller;
P6.8 proves no-write behavior separately. P2.7 and P6.11 use disposable roots only; live
P7.2 apply/repair/rollback remains separately owner-gated.
