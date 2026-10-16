# ADR 0063: Modules reach each other through partner commands with JSON output

## Status

Accepted

## Context

A hub module sometimes needs data or a service of another module. [ADR 0058](0058-bridges-as-hub-units-and-partner-lookup.md)
fixed the lookup for bridges only; the hub modules `maind`, `analyst` and `harness` still imported each other and
named each other's folders.

## Decision

- **Call.** A module calls a partner as a process through the partner's public command that prints JSON. The shape of the
  output is the partner's contract: a schema under the partner's `schemas/<name>/v1` and a test of the partner.
- **Lookup.** `aicore.util.partners.partner_command(name)` returns the command line: the deprecated variables of the
  consumer (one warning), `SKM_<NAME>_BIN`, `SKM_<NAME>_ROOT/bin/<name>`, then `<name>` on `PATH`. For `planner` the order
  is `PLANNER_PLAN_PY`, `PLANNER_ROOT/scripts/plan.py`, the deprecated `SKM_TASK_ROOT` and then `planner` on `PATH`.
  There is no step for a neighbouring folder or the root of the monorepo. `require_partner` and `run_partner_json` are the
  helpers that raise `PartnerUnavailable` and `PartnerError`.
- **Absence.** A missing partner is `PARTNER_UNAVAILABLE: <partner> not found (set SKM_<P>_ROOT or put <partner> on PATH)`
  on stderr and a degradation of the command (a skipped source, a `skip` in a doctor), never a crash.
- **Hooks.** Hooks that are installed into projects run without `aicore`; they repeat the same ladder in their own code.
- **Tests.** `bash scripts/test-integration.sh` runs the module tests that need partners with the partners of the hub;
  a test that needs a partner is skipped when the lookup finds none.
- **No `bridges/` folder.** A bridge is justified when adapter logic belongs to neither side (planner and orch). Here the
  contract and the logic belong to the partner, so no new bridge is created.

## Alternatives considered

- A module that needs another module's data as an in-process import: rejected, it breaks the rule that a module imports only itself and `aicore`.
- A bridge for every pair of modules: rejected, it would hold no logic of its own.

## Consequences

- A module that moves into its own repository keeps working when its partners are on `PATH`.
- The boundary check can forbid imports and paths of other modules without exceptions.

## Supersedes

Refines [ADR 0058](0058-bridges-as-hub-units-and-partner-lookup.md); that ADR is not replaced.
