# orch

Internal, engine-neutral orchestration contracts for the swissknifeman monorepo.
Status: **internal, not published**. The package uses only the Python standard library, `orch` and the `aicore` foundation.

- [Quickstart](quickstart.md) — what a real project needs, what a run changes, the switches that matter.
- [How work flows](flows.md) — diagrams: the parts, one piece end to end, the item lifecycle, correction rounds and limits, the review decision, batches, questions and the advisor, provider failures, stop and recovery, setting layers, debug mode.
- [exec/v1 contracts](contracts.md) — nine document kinds, conventions, contract changelog.
- [Engine Port](engine-port.md) — operations, run states, binding capability matrix.
- [Role/provider matrix](../README.md#roleprovider-matrix) — launch entries and explicit refusals for every role/provider pair.
- [Configuration](configuration.md) — the `[orch]` section, layers, engine choice, digest.
- [Docker environment](docker-environment.md) — optional check of the Docker daemon (`orch doctor`, `scripts/docker-env-check.py`) and the rootless setup.
- [Run-policy packs](run-policies.md) — shipped policies, cases, `orch.py policy`.
- [Events](events.md) — `orch.run.*` types, data contracts, emission rules, fixtures.
- [Work source](work-source.md) — the `orch:work-source` port, its contract and the `orch.py source` cycle.
- [Conductor](conductor.md) — `orch conduct`: the chain of roles of a piece of work, run options, progress, resume,
  the observer, and which files are committed.
- [Ownership of a run](conductor.md#ownership-of-a-run) — leases, one conductor per checkout and orphaned runs.
- [Recovery after a crash](conductor.md#recovery-after-a-crash) — interrupted steps, receipts and local durability.
- [Token usage and limits](conductor.md#hard-token-limits-and-resume) — accounted fresh tokens, incomplete usage, hard limits and limit raises on resume.
- [gui-orch README](../../../bridges/gui-orch/README.md) — used/available routes, prompt metadata, budget, gates and owner/orphaned views.
- [Deferred audit proposals](../../../roadmap/2026-10-19-audit-deferred.md) — measurable triggers, module owners and audit sources.
- [Agent mode](agent-mode.md) — the procedure for an agent that picks its own pieces: ready lanes of the work source, `orch conduct run --items`, `status`/`observe`, `resume`/`settle`.
- [Stubs and provider/model-family variants](conductor.md#stubs-additional-instructions-of-the-roles) — additional instructions of the roles by machine and project: `orch.py stubs publish|list|show`, `[orch.stubs]`, the snapshot of a run and route-specific variants on fallback/resume.
- [Research sources](research.md) — `[orch.research]`: `command`, `filesystem` and `mcp-stdio` sources, retries on `BROWSER_BUSY`, `orch.py research`, a Perplexity example.
- [Conformance](conformance.md) — scenario catalogue, `orch.py conformance`, write confinement.
- [Architecture](architecture.md) — package boundaries, dependency rule, layout.
- [Adding an engine](adding-an-engine.md) — steps to add a binding.
