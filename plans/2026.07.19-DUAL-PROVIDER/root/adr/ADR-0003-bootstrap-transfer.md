# ADR-0003 — closed D104 bootstrap-transfer admission

**Status:** Accepted — Approval Owner D104

## Context

The normal P2 engine correctly refuses an unmanaged `.codex/hooks.json`. The owner approved one
exact bootstrap preimage only after the P7.2 no-write preflight proved that normal repair cannot
create the paired lifecycle handler safely.

## Decision

Add a v1.2.0 closed `core.provider_lock` admission with an immutable descriptor and one planner.
It verifies the exact D104 decision, SHA-256 preimage, two project-relative targets, two artifact
IDs and absent lock before every transaction write. It writes a recoverable first-target backup,
the two targets, then one canonical lock. Failure rolls back only exact transaction-created state.

## Consequences

Ordinary create/update/repair and every non-D104 ownership conflict remain fail-closed. No second
lock format, discovery, provider branch or live-root operation is introduced. P5.8 supplies native
Codex composition; P6.7 supplies the caller; P6.8 proves no-write behavior separately.
