# ADR 0081: GUI reaches domains only through bridges gui-<module> and the aicore plugin protocol

## Status

Accepted

## Context

The GUI shows and changes the data of other modules (hub fleet and units, planner plans, orch runs). A module may
depend only on its own library and on aicore (ADR 0002) and reaches partners only through bridges or events (ADR 0003).
`gui` has `destination: own-repo`, so any import or path of another module would break when it moves out.

## Decision

- **Host and adapters.** `packages/gui` is the host. Each domain gets a bridge `bridges/gui-<module>` (`gui-hub`,
  `gui-planner`, `gui-orch`) that carries a `gui.json` contribution and an aicore `extension.json`, and calls the
  public command line of the domain owner.
- **Extension points.** `gui` declares `gui:query` (read-only queries, answer `view-data/v1`) and `gui:command` (short
  commands) in its `unit.json`; bridges and external extensions implement them through the aicore plugin protocol.
- **One path.** Hub bridges and external extensions (which declare `provides.gui` in their `extension.json`) go
  through the same resolver and conformance.
- **Owners stay unchanged.** A domain module does not change for the GUI; a missing public ability of its command line
  (for example a `--json` output) is added as its own additive change with its own tests.
- **Discovery.** Units come from `swissknifeman units list --json` or `SKM_UNITS_PATH`.

## Alternatives considered

- `gui` imports module libraries directly: rejected, breaks ADR 0002 and the move of modules to their own repositories.
- A `gui.json` inside each domain module: rejected, the owner would have to know the GUI contract and change for it.

## Consequences

- The boundary is checked mechanically: `python3 scripts/ecosystem-units.py check --strict` forbids the names of
  other module folders in `gui` files.
- A query costs one short process; read-only queries are cached for the time the contribution declares.

## Supersedes

None. Applies ADR 0002 and ADR 0003 to the GUI.
