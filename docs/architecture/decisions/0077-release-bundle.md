# ADR 0077: Release bundle: compat manifest, schema package, attestation and checksums

## Status

Accepted

## Context

[ADR 0023](0023-releases-and-supply-chain.md) named what a release holds now: checksums, the changelog, a compatibility
manifest and a package of schemas, plus the existing attestation. Only the attestation existed.

## Decision

- **Command.** `aicore release bundle --root ROOT --tag TAG --out DIR`, reached as `swissknifeman release bundle`.
- **Files.** `compat.json` (`compat-manifest/v1`: umbrella version and tag; for each module and bridge version, stability,
  destination, `requires` and contracts with hub-relative paths), `schemas-<tag>.tar.gz` (deterministic, `index.json`
  first), `release-attestation.json` (`aicore.release.attestation`, taken at `HEAD`) and `SHA256SUMS` (`sha256sum`
  format).
- **Safety.** `DIR` must be absent or empty; nothing is written outside it.
- **Not included.** SBOM, signatures and SLSA provenance wait for the publication trigger.

## Alternatives considered

- Publishing each module's schemas separately: rejected while modules ship from one repository.
- Adding signatures now: rejected, modules are stdlib-only with no wheels, so the gain is small.

## Consequences

- A consumer can verify the files with `sha256sum -c` and read the compatibility of the release without a checkout.
- Run the bundle on a committed tree: the attestation reads `HEAD`.

## Supersedes

None.
