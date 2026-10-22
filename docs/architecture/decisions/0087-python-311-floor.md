# ADR 0087: Minimum Python is 3.11

## Status

Accepted

## Context

The hub floor was Python 3.9 ([ADR 0032](0032-ready-made-or-own-and-non-goals.md)). CPython 3.9 reached
end of life on 2025-10-31 ([PEP 596](https://peps.python.org/pep-0596/#lifespan)) and CPython 3.10 on
2026-10-01 ([PEP 619](https://peps.python.org/pep-0619/#lifespan)); both are unsupported in the
[Python developer's guide](https://devguide.python.org/versions/#unsupported-versions). That floor forced
a vendored TOML reader, hand-rolled time parsing and `total=False` TypedDicts instead of `NotRequired`.
`gui` already requires 3.11.

## Decision

`aicore.MIN_PYTHON` is `(3, 11)` and is the only floor. `scripts/check-env.sh` and `install.sh` refuse an
older `python3` before they change the machine. The CI test matrix is 3.11, 3.13 and 3.14. TOML is read
only through `tomllib` in `aicore.config.toml`; the vendored `tomli` tree is removed. Module code stays
inside the 3.11 grammar (no PEP 695 `type` aliases and no `def f[T]`).

## Alternatives considered

- Stay on 3.9 and generate TypedDicts with a `total=False` base: rejected, 3.9 and 3.10 are end of life
  and the workarounds remain.
- Floor 3.10: rejected, 3.10 ended on 2026-10-01 and still has no `tomllib` and no `NotRequired`.

## Consequences

- A machine whose `python3` is 3.9 or 3.10 must install Python 3.11 or newer before `install.sh`.
- `gui.MIN_PYTHON` stays `(3, 11)`, equal to the hub floor.
- A later item may emit `NotRequired`. Time and lock helpers are unchanged here.
- Lowering the floor means reverting this record.

## Supersedes

Supersedes the vendored-reader half of [ADR 0036](0036-toml-vendored-tomli-and-minimal-editor.md).
The comment-preserving editor in that record stays. Refines the minimum stated in ADR 0032.
