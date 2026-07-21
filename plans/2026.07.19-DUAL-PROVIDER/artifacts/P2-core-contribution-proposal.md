# P2.1 core contribution proposal — deterministic provider artifact kernel

**Status:** Accepted — Approval Owner D75, 2026-07-20.

**Initiator:** `2026.07.19-DUAL-PROVIDER` P2.1
**Shared package:** repository-root `core` (stdlib-only)

**Decision:** D75 accepts the exact K1–K6 candidate below. It authorizes only P2.1 implementation; P2.2+, provider delivery, live carriers, FOREMAN, fleet, and target writes remain excluded.

## Rule-of-Three evidence

| Current independent consumer | Existing repeated concern | Why it cannot be the shared owner |
|:--|:--|:--|
| `skiller` | `skills-lock.json`, source/content hashes, read-only `plan_sync`, managed-only prune and ownership conflicts | Its skill-specific schema/semantics do not apply to harness or maind artifacts. |
| `harness` | timestamp-free generated provenance, rendered-byte hash, safe-apply/conflict classification and drift doctor | It is Claude agent-pack code; using it upstream reverses dependencies for skiller/task/maind. |
| `maind` | deterministic managed blocks/templates plus hash/drift health diagnostics | It is a hub consumer and must not become a generator imported by package adapters. |

The repository recon (`findings/P2-artifact-engine-recon-2026-07-19.md`) therefore demonstrates three present, independent repetitions of canonical bytes, provenance/hash, and managed-artifact planning. This is a Rule-of-Three **go**, not projected reuse.

## Existing extension-point survey

`core.io` already owns atomic-write primitives; `core.block` owns deterministic managed-block construction and a short content hash. Neither models frozen artifact identity/provenance, canonical source envelope, full SHA-256 digest, target-relative path validation, adapter version, or a pure rendered result. They remain reused primitives, not a sufficient artifact-kernel extension point.

No package-specific sync/agent-pack/health policy is moved into `core`.

## Alternatives

| Alternative | Decision | Reason |
|:--|:--|:--|
| Keep three package-local engines | Reject | The shared invariant has already diverged three times and P3–P6 would multiply it. |
| Make `harness.agentpacks` the common generator | Reject | It forces unrelated consumers to depend on Claude-oriented package code. |
| Generic template DSL or import-time/global registry | Reject | It introduces discovery, provider branches, import-order coupling and a service locator. |
| Flat pure `core` seam with explicit caller inputs/adapters | Recommend | It shares only the proven invariant and preserves package ownership/dependency direction. |

## Proposed minimal public API

This is the complete proposed P2.1 public surface; it is additive to `core.__all__` and changes no existing P1 protocol.

| Symbol | Kind | Responsibility |
|:--|:--|:--|
| `ArtifactSource` | frozen dataclass | Source ID, normalized project-relative POSIX path, exact content hash. |
| `ArtifactTarget` | frozen dataclass | Target-relative POSIX path and frozen managed-boundary descriptor. |
| `ArtifactAdapterIdentity` | frozen dataclass | Adapter ID/version, Provider ID, accepted capability requirements. |
| `ArtifactRenderRequest` | frozen dataclass | Artifact ID, ordered sources, target, adapter identity, ordered overrides, semantic parameters and caller-supplied renderer. |
| `ArtifactProvenance` | frozen dataclass | Exact frozen-contract provenance fields and deterministic hashes. |
| `ArtifactRenderResult` | frozen dataclass | Managed bytes, target and provenance; no write/apply state. |
| `canonical_json_bytes(value)` | pure function | UTF-8 JSON bytes: sorted keys, compact separators, `ensure_ascii=False`. |
| `sha256_digest(bytes_)` | pure function | `sha256:<64 lowercase hex>` digest. |
| `validate_target_path(path)` | pure function | Reject absolute, empty, `.`/`..`, or escaping paths. |
| `plan_artifact_render(request)` | pure function | Validate, call supplied renderer once, and return deterministic provenance/result. |

The request owns a P2-local protocol-compatible renderer callable. P1's frozen `ProviderAdapter` has identity/capability metadata but no renderer operation or adapter version; it is not mutated.

## Contract and dependency anchors

The implementation copies `provider-artifact-contract.md` v1.0.0 (D55) exactly: sorted canonical source records, source-envelope JSON/hash rules, rendered hash over contract-defined managed bytes, path-independent artifact ID, sidecar/lock authoritative provenance, and no self-referential inline rendered hash. Timestamp, locale, cwd, environment/host paths, randomness, mapping insertion order, discovery, global registration, and `if provider == ...` branches are forbidden.

Capability requirements/Provider IDs pass through the frozen capability/config contracts; P2.1 creates no second support matrix. P2.1 has no filesystem write, lock/drift/apply/repair, catalog selection, CLI, or package/provider render semantics.

```text
skiller / harness / maind  -- explicit request + renderer -->  core.provider_artifact
                                                                  |
                                                                  +--> core.io / stdlib hashing
```

`core` imports no `packages.*`, provider SDK, renderer implementation, CLI, discovery, or consumer code. Consumers depend on `core`; they never depend on each other through it.

## SemVer and release consequence

The proposed change is a backward-compatible **minor** `core` release: public symbols are added and existing behavior is unchanged. Version/changelog/release-carrier work and downstream adoption are deferred until implementation. Any later public removal/rename, tightened input, weakened output, or changed bytes/hash semantics is breaking and requires a major release plus migration guide.

## Approval boundary

Approval authorizes only P2.1 implementation paths. It does not authorize P2.2 locks/apply/repair, P2.3 registry, P3–P6 adapters, live config, FOREMAN, fleet, or target writes.

Proposed exact owner decision:

```text
APPROVE P2.1 CORE-ARTIFACT K1-K6 AS WRITTEN
```

1. **K1:** Rule-of-Three evidence and extension-point survey justify a shared `core` seam.
2. **K2:** the ten-symbol list above is the complete P2.1 public API.
3. **K3:** artifact contract v1.0.0 bytes/hash/provenance/path invariants are exact; P2.1 has no lifecycle-write authority.
4. **K4:** callers supply explicit inputs/renderer; `core` imports no consumer/provider code and P1 protocols stay unchanged.
5. **K5:** this is a backward-compatible `core` minor release; later breaking changes require major+migration.
6. **K6:** authority is limited to P2.1; P2.2+, provider delivery, live carriers, FOREMAN and fleet remain excluded.

Any change to K1–K6 is a revision request, not partial approval.
