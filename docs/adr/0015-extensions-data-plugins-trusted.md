# ADR 0015: Extensions are data; executable plugins are trusted-only

Status: proposed
Date: 2026-10-25

## Context
Skills, steering, profiles and templates are instructions, not code; third-party Python in the API process has
full access.

## Decision
Skills, steering, agent profiles, workflows, plan templates, prompt blocks and integration bundles are versioned
resources in packs (`pack.toml`) with digest and provenance. Overlays are operator packs contributing a
config fragment (`pack` layer) and resource overrides; personal content (author overlay `axioma`) lives outside
the core. Executable extensions (runtime adapters, check runners, stage handlers, integration targets) are loaded
only from entry points `skm.plugins` listed in `plugins.allowed` at instance level. Resources can never widen
permissions.

## Alternatives considered
- Plugin marketplace with untrusted code: deferred.

## Consequences
Content migration is a data task; core stays neutral.

## Compatibility
Legacy skill provenance (`upstream.json` strategies) is preserved in resource manifests.

## Verification
Security test: a profile/skill declaring wider permissions is rejected at load and at context assembly.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E15 fixes seven roles with profile variants. E16 keeps resources/ as the sole pack source, packaged as skm/_resources. E30 restricts pack config trust and security ceilings. E32 pins pack versions for run catalog/resource resolution.
