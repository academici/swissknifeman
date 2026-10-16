# ADR 0023: Releases and supply chain: what is needed now and what waits for a trigger

## Status

Accepted

## Context

Modules are stdlib-only and are not published as wheels, so full supply-chain tooling gives little today.

## Decision

A release contains checksums, the changelog, a compatibility manifest (module and contract versions) and the schema
package; the existing release attestation is used. A project stores a provisioning stamp (which module versions
configured it), which the upgrade needs. On the trigger "public publication of modules": SBOM (CycloneDX),
signatures (Sigstore), SLSA provenance and an optional cached online compatibility catalogue. On the trigger
"modules move to separate repositories": an ecosystem lock, a release train and shared organisation workflows.

## Alternatives considered

- Add SBOM, signing and provenance now: rejected, no published artifacts to protect yet.

## Consequences

- Triggers are explicit, so the work is not forgotten and not done early.

## Supersedes

None.
