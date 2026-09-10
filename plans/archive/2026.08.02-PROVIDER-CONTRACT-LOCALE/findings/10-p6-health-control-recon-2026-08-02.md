# P6 Brain and fleet-health reconnaissance

**Date:** 2026-08-02

## Repository facts

- `packages/maind/lib/maind/health.py` proves one project's memory daemon, mAInd MCP,
  memory-hook mode, round-trip, MCP hygiene and provider trust. Its strict verdict does not
  include the P3 adapter status, capability activation, skill dependency closure, first-turn
  budget, locale readback or P5 migration result.
- `packages/maind/lib/maind/projects.py` exposes a read-only fleet `status`, but calls
  `probe_project` without a provider context. The result therefore omits the provider-trust
  rows that single-project `maind health` can expose and has no exact-set P0/P5 evidence gate.
- `packages/maind/lib/maind/doctor.py --provider-trust` aggregates only the trust axis. A green
  trust row is not a provider/capability-health verdict.
- `packages/harness/lib/harness/provider_audit.py` proves deterministic package catalog and
  adapter conformance for both providers. It does not inspect a consumer project's effective
  settings, desired selection or adapter readback.
- `packages/harness/lib/harness/settings_audit.py` contains a bounded Codex-specific reader and
  checks, but the public `harness doctor --settings` dispatcher does not accept or route
  `--provider codex`; the attempted public invocation refuses with `unknown flag`.
- `packages/skiller/lib/skiller/status.py` reports channels, duplicates, dead local entries and
  a registry-skill budget. `resolve_requires_bfs` deliberately lets an explicit exclusion win
  over a required dependency and emits only a warning. The JSON status has no exact
  unsatisfied-dependency row, so the known Brain `session-observer`/`shared-memory` conflict
  cannot be a deterministic fleet gate yet.
- `packages/skiller/lib/skiller/budget.py:first_turn_report` is the current owner of measured
  first-turn inputs and budget verdicts. P6 must consume this owner instead of reproducing token
  math in mAInd.
- P3.3 already owns provider-scoped status, ownership, drift and migration diagnostics; P4.6
  owns repository/locale acceptance; P5.4 owns migrated versus unresolved outcomes. P6 may
  compose these results but must not reread provider files to invent replacement semantics.
- The live mAInd graph is an independent plane and is not a fleet membership source. P6's
  project set must remain the sealed P0 set, rebound through the live registry only as the P5
  locator boundary permits.

## Preflight observations

- `codex doctor --json`, `harness doctor`, `harness doctor --provider-audit --json`,
  `maind health --cwd --strict --json` and plan lint are green for SKM at this observation.
- `maind projects status --project swissknifeman --json` is green on its existing generic axes
  but contains no provider rows. That is a schema boundary, not proof that both providers are
  healthy.
- `skiller status --target . --json` is readable but does not expose a dependency-closure
  verdict or the full first-turn measurement.
- The canonical `maind health --cwd` form takes a boolean flag, not a path value. An earlier
  `--cwd <path>` preflight refusal was caller misuse; the corrected worktree-local command is
  green and is not an environment defect.
- The working tree already contains broad unrelated/uncommitted package and generated-artifact
  changes. This design pass changes plan files only and does not treat current worktree output
  as shipped P6 evidence.

## Verification

- Repository claims were verified from the named source files and the read-only preflight
  outputs above.
- P6 introduces no dependency, third-party API or new provider-capability assertion. Provider
  support levels remain pinned to the repository capability manifest and P1/P3 contracts.
- **RAG:** no new query; all decision-bearing facts in this pass are repo/plan-grounded.
- **Unverified -> repeat pass:** terminal P0/P1/P3/P4/P5 contract versions, public status APIs,
  exact Brain action inventory and fleet project set do not exist yet. P6 execution must rebind
  them from committed Completion Notes and stop on any incompatible identity or schema.
- **Workarounds/[POSSIBLE-DEFECT]:** none. A plan-local evidence exporter may sequence public
  read-only checks, but recurring health semantics belong to package-owned Skiller/Harness/mAInd
  surfaces and the versioned P6 contract.
