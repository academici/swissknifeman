# ADR 0069: Module doctors print check-result/v1 and keep probe and repair apart

## Status

Accepted

## Context

Each module printed its own diagnostic text. The hub needs one machine-readable shape, and a probe must not change
state.

## Decision

- **Output.** `maind doctor --json`, `analyst doctor --json` and `harness doctor --json` print a list of `check-result/v1`
  documents. The text form is one line `<status> <check_id>: <observed>` per check; exit 1 means a `fail`.
- **Declaration.** `unit.json` `provides.doctor` lists every check with its probe command and the output `check-result/v1`.
- **Probe writes nothing.** A test snapshots the file system; `maind` no longer creates its state directory to probe it.
- **Repair is separate.** `maind health --plan-repair` only reads (`--json` prints `{project, actions}`) and
  `maind health --apply-repair` writes; `--fix` is an alias with one `MAIND_HEALTH_FIX_DEPRECATED` warning. A `repair`
  field of a result names both commands.
- **Python floor.** Every doctor, including skiller, compares against `aicore.MIN_PYTHON` (3.9).
- **Secrets.** No doctor prints a secret; a test plants a sentinel value and searches the output.
- **Aggregation.** A command that collects all module doctors belongs to the hub.

## Alternatives considered

- A text-only doctor: rejected, tools cannot read it.
- `--fix` that also plans: rejected, a command that may write needs a name that says so.

## Consequences

- A new check is one more document in the list and one more `provides.doctor` entry.

## Supersedes

None.
