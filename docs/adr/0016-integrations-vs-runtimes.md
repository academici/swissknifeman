# ADR 0016: Client integrations are separate from agent runtimes

Status: proposed
Date: 2026-10-25

## Context
Legacy `harness` mixes environment projection, hook enforcement and run-time concerns; the word "harness"
means a runtime elsewhere.

## Decision
`runtimes` owns unattended session lifecycle (start/stream/cancel/resume/result, capabilities, usage).
`integrations` owns projection of instructions, skills, permissions, hooks, MCP entries and agent packs into a
checkout for interactive use, with three ownership kinds (managed file, managed block, merged JSON keys), drift
detection and doctor. Provider hooks call a single `skm hook <event>` entrypoint backed by pure policy cores.
Default permission profile is `workspace-contained`; never bypass by default.

## Alternatives considered
- One provider adapter covering both: rejected — a client may have integration without a headless runtime.

## Consequences
Two adapter families per provider.

## Compatibility
Legacy ownership model (`*.pack-new`, markers, adoption with pre-image) is ported.

## Verification
Golden tests per target; drift tests; hook cold-start budget test.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).
