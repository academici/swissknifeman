# P4 task-command contribution review

**Item:** P4.2  
**Decision authority:** D79 applied against frozen D84  
**Verdict:** ACCEPTED — additive, contract-preserving task-package contribution

## Rule-of-Three gate

The command catalog is already consumed by the Claude task plugin and is now required by the
Codex task plugin; P5–P7 and the post-P7 FOREMAN reconcile are named downstream consumers in
D84. A consumer-local implementation cannot preserve one stable `task:*` identity, exact-set
inventory, source hashes, routing metadata and provider-qualified diagnostics across those
surfaces. The shared seam therefore belongs to `packages/task`.

## Existing extension-point survey

- Canonical bodies remain `packages/task/commands/*.md`; no second editable body tree is added.
- The frozen P2 artifact kernel remains the provenance/hash primitive; task owns only its
  semantic catalog and provider renderer.
- The P3 publication contract already permits sibling package-owned Codex projections and
  deterministic cache-contained copies. No skiller registry or generic plugin framework is
  introduced here.

## Alternatives

1. Hand-maintain root `.agents/skills/task-*`: rejected; it is protected bootstrap state and
   would create a second semantic command set without exact-set or source-drift gates.
2. Move task command semantics into skiller publication code: rejected; it reverses the
   dependency direction and makes skiller own a sibling package's command contract.
3. Task-owned immutable catalog plus one named Codex renderer: accepted; it is the smallest
   seam that preserves D84 and emits self-contained deterministic cache artifacts.

## Accepted contract

- One frozen immutable record per exact canonical command, with stable ID, source digest,
  routing, capabilities and provider projection references.
- Explicit command root, routing carrier, mapping and capability inputs only; no cwd, home,
  import-registry or environment discovery.
- All catalog/mapping/capability/route diagnostics are computed before any write.
- Generated Codex skills contain a wrapper plus a locked runtime copy of the canonical body;
  the copy is provenance-labelled output, never an editable source.

## Compatibility and SemVer

The contribution is additive and backward compatible: existing Claude command files and plugin
manifest are unchanged. The task package gains a new Codex projection without removing or
renaming a public identity, so this is a minor-class capability addition within the existing
`0.2.0` package/plugin line. D84 identity, routing axes, diagnostics and plan literals are not
changed; any such change remains an owner-level contract revision.

## Approval record

Accepted under delegated Owner Approval D79 because the implementation is evidence-backed,
contract-preserving, within P4.2 Files and reversible. No new public abstraction outside the
task package and no authority over live installs, root bootstrap adapters, FOREMAN or fleet is
created.
