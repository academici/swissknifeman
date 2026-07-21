# P5 harness contribution review

**Item:** P5.2
**Decision authority:** D79 applied against frozen D85
**Verdict:** ACCEPTED — additive, contract-preserving harness contribution

## Rule-of-Three gate

The frozen profile/surface catalog is consumed by the existing Claude settings and
permissions surfaces, the new Codex projection, and declared P5.3–P5.5/P6–P7
consumers. A consumer-local implementation would duplicate profile identity, security
gates, and repair semantics. The shared seam therefore belongs to `packages/harness`.

## Existing extension-point survey

- `core.provider_config` supplies the already-frozen effective provider selection and
  provenance; `core.provider_artifact` supplies deterministic render plans and ownership
  semantics. Neither package imports harness.
- `harness.settings`, `permissions`, and `settings_audit` remain named Claude compatibility
  seams. They are not relabelled as a universal merge model.
- The new catalog is an explicit immutable package resource. Named Claude and Codex
  renderers consume it independently; no filesystem/import discovery or output translation
  is introduced.

## Alternatives

1. Continue treating `configs/claude-code` as the common source: rejected; Claude keys
   become a hidden provider-neutral API.
2. Put profile/render semantics in `core`: rejected; it makes core own provider content and
   reverses the frozen dependency direction.
3. Add an explicit harness catalog with named provider adapters: accepted; it is the
   smallest additive seam that preserves D85 and existing Claude behavior.

## Accepted contract

- Common records contain stable profile/surface identity and independent trust, approval,
  and sandbox requirements; they contain no provider paths, hooks, or resolved secrets.
- Profile resolution takes explicit provider configuration, capabilities, trust, and operation
  inputs and returns one immutable semantic render plan or structured no-write diagnostics.
- `trusted-full-access` requires a trusted repository plus an exact operation and target;
  defaults, project, fleet, legacy, and unknown inputs are rejected before rendering.
- Claude and Codex are rendered independently from the same semantic plan. Claude preserves
  its existing merge-only settings/permissions behavior and named settings audit.
- One semantic render plan feeds dry-run, write, check, and repair. Tests use temporary
  targets only; P7 remains the only self-host/live apply authority.

## Compatibility and SemVer

This is an additive minor-class capability within harness. Existing Claude presets,
`apply-permissions.sh`, and settings-doctor behavior remain independent compatibility
goldens. D85 profiles/surfaces/security rules and frozen P1/P2 contracts are unchanged.

## Approval record

Accepted under delegated Owner Approval D79: the implementation is bounded to P5.2 Files,
consumes frozen contracts, and introduces neither a new core abstraction nor authority over
user-global settings, bootstrap, FOREMAN, or fleet state.
