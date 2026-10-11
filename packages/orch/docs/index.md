# orch

Internal, engine-neutral orchestration contracts for the swissknifeman monorepo.
Status: **internal, not published**. The package uses only the Python standard library, `orch` and the `aicore` foundation.

- [exec/v1 contracts](contracts.md) — nine document kinds, conventions, contract changelog.
- [Engine Port](engine-port.md) — operations, run states, binding capability matrix.
- [Configuration](configuration.md) — the `[orch]` section, layers, engine choice, digest.
- [Run-policy packs](run-policies.md) — shipped policies, cases, `orch.py policy`.
- [Events](events.md) — `orch.run.*` types, data contracts, emission rules, fixtures.
- [Work source](work-source.md) — the `orch:work-source` port, its contract and the `orch.py source` cycle.
- [Conductor](conductor.md) — `conduct.py`: the chain of roles of a piece of work, run options, progress, resume,
  the observer, and which files are committed.
- [Conformance](conformance.md) — scenario catalogue, `orch.py conformance`, write confinement.
- [Architecture](architecture.md) — package boundaries, dependency rule, layout.
- [Adding an engine](adding-an-engine.md) — steps to add a binding.
