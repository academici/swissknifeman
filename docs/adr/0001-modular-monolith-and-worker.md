# ADR 0001: Modular monolith in one distribution plus a separate worker process

Status: proposed
Date: 2026-10-25

## Context
Legacy SKM is ten packages installed by symlink, connected by four bridge mechanisms (CLI subprocess calls,
plugin protocol, partner lookup, umbrella aliases). Independence was paid for with duplication (locator
fragment in 33 files, `partners.py` ×4, a vendored validator) and with process spawning on every GUI query.

## Decision
SKM v2 is one Python distribution `skm` (src layout) with bounded-context modules inside, one composition root,
and in-process calls through module facades. Agent work runs in a separate `skm worker` process, never inside the
API process. Deployment units: `skm serve` (API + background services), `skm worker`, PostgreSQL, `web/`.

## Alternatives considered
- Keep multi-package layout with bridges: rejected — duplication, slow cross-module calls, weak integrity.
- Microservices: rejected — no scale need; boundaries belong in contracts first.
- Independent distributions per module: deferred until a real external consumer needs a separate lifecycle.

## Consequences
- Module independence is enforced by import rules and contracts (ADR 0002/0003), not by packaging.
- Optional modules can be disabled by configuration.

## Compatibility
Legacy CLIs are not preserved; import of legacy data is a separate phase (P14).

## Verification
Architecture tests (ADR 0002); e2e scenario runs API and worker as separate processes.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E01 places the distribution at the repository root. E02 requires all 14 module declarations before behavioral implementation.
