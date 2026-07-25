# ADR-0002 — deterministic provider artifact kernel in `core`

**Status:** Accepted — Approval Owner D75
**Date:** 2026-07-20
**Scope:** P2.1 only. D75 authorizes the frozen K1–K6 public `core` symbols and no further scope.

## Context

`skiller`, `harness`, and `maind` independently implement pieces of deterministic artifact generation: canonical hashes, timestamp-free provenance, managed boundaries, and read-only planning/diagnostics. The frozen provider-artifact contract v1.0.0 requires one model for identity, canonical source envelopes, hashes, provenance and target-relative paths before P3–P6 adapters exist.

`core.io` and `core.block` are reusable primitives but do not express that model. Promoting a package implementation would reverse dependencies; retaining three engines preserves drift.

## Decision candidate

After owner approval, P2.1 adds one flat stdlib-only `core.provider_artifact` module with the complete additive surface listed in `artifacts/P2-core-contribution-proposal.md`: immutable source/target/adapter/request/provenance/result values, canonical JSON and SHA-256 helpers, relative-target validation, and one pure render-plan function that receives a caller-supplied renderer.

The module does not discover inputs, inspect environment/cwd, select adapters, write files, own locks, classify drift, repair targets, emit CLI output, import consumers, or branch by provider. It does not extend the frozen P1 `ProviderAdapter`; P2's request uses its own renderer callable plus explicit adapter identity/version.

## Alternatives

1. Keep package-local engines — rejected: three current consumers already repeat the invariant.
2. Promote `harness.agentpacks` — rejected: Claude-specific package becomes an upstream dependency.
3. Generic template framework/global dynamic registry — rejected: discovery/service-locator and provider-branch surface is premature.
4. Flat pure `core` kernel with explicit caller adapters — recommended: minimal Rule-of-Three seam with correct dependency direction.

## Consequences

- Additive public API implies a minor `core` release; breaking changes later require major+migration.
- Frozen artifact-contract byte/hash/provenance rules become testable before P2.2 lifecycle writes.
- Packages retain render semantics and supply adapters explicitly.
- P2.2 owns locks/drift/apply/repair and P2.3 owns capability-aware adapter selection; neither is implied here.

## Approval condition

D75 accepted K1–K6 in `artifacts/P2-core-contribution-proposal.md` through the exact Owner reply `APPROVE P2.1 CORE-ARTIFACT K1-K6 AS WRITTEN`. It authorizes `core` source/export/test only for P2.1; release metadata, live carriers, FOREMAN, and fleet remain unauthorized.
