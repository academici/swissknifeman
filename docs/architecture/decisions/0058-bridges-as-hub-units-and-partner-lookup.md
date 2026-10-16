# ADR 0058: Bridges are hub units; partners are found by variable or command, never by path

## Status

Accepted

## Context

[ADR 0003](0003-three-kinds-of-links-and-bridges.md) introduced bridges between planner and orch, but the bridges lived
inside the packages they connect and found a partner by looking at a neighbouring folder.

## Decision

- **Place.** A bridge is a unit of the hub: `bridges/<id>/` with `unit.json` (kind `bridge`, destination `hub`, `requires`
  for both sides and the foundation, `protocol` range, `dev.test`), a `README.md`, `scripts/test.sh` and `tests/`.
  The bridges are `planner-orch`, `orch-skiller` and `orch-harness`.
- **Lookup.** A partner is found by an explicit variable (`PLANNER_PLAN_PY` or `PLANNER_ROOT`, `SKM_ORCH_ROOT`,
  `SKM_SKILLER_ROOT`, `SKM_HARNESS_ROOT`), then by a command on `PATH`. A missing partner is
  `BRIDGE_PARTNER_UNAVAILABLE` with exit 3. A bridge never reads a neighbouring path. The foundation is found by the
  canonical locator with a third step, `packages/aicore` of the hub that holds the bridge.
- **Calls.** A bridge imports the standard library and `aicore` only; partners are called as processes by their command
  line and JSON. The planner bridge writes into a plan only through `plan.py`.
- **Registration.** The planner finds bridge directories through the `bridges.roots` setting; the verb is
  `plan.py bridge planner-orch <verb>`. The old bridge verb `orch` has no alias. The bridge `bridges/task` of orch
  (model routing) is removed, the routing belongs to the `aicore` model catalog.
- **Check.** `python3 scripts/ecosystem-units.py check` validates the units and scans bridge code for imports of
  partner packages and for the paths of other modules; `bash scripts/test-bridges.sh` runs every bridge test.

## Alternatives considered

- Bridges inside the packages: rejected, the package would name its partner.
- Discovery by sibling folders: rejected, it breaks once a module moves to its own repository.

## Consequences

- A module that moves out of the repository keeps its bridge in the hub; the partner is then found on `PATH`.
- Tests that need a partner are skipped when it is not found.

## Supersedes

Refines [ADR 0003](0003-three-kinds-of-links-and-bridges.md); that ADR is not replaced.
