# ADR 0029: Finding aicore through one canonical locator fragment

## Status

Accepted

## Context

A module may not name the path of another module, yet its wrapper and its test runner must find `aicore`: in the hub
it is a neighbouring folder, in a standalone copy it is a vendored folder.

## Decision

`packages/aicore/scripts/aicore-locator.sh` is the one canonical bash fragment. It is copied verbatim between the
markers `# --- aicore locator ---` and `# --- end aicore locator ---` into `bin/<cli>` and `scripts/test.sh` of the
modules that require `aicore`. The search order is `$AICORE_ROOT` (when set and wrong, an error, never a fall
through), then `<module>/_vendor/aicore`, then `<module>/../aicore`. A candidate qualifies when its `unit.json` has
`"id": "aicore"`. The result is the exported `AICORE_ROOT` and `AICORE_LIB=$AICORE_ROOT/lib`, which the wrapper puts
on `PYTHONPATH`. A miss prints `AICORE_NOT_FOUND` with the hint to set `AICORE_ROOT` and exits with code 2.
`scripts/test-aicore-locator.py` keeps the copies identical and tests the behaviour. During the shim window `core`
itself adds `<repo>/packages/aicore/lib` to `sys.path` when `aicore` is not importable.

## Alternatives considered

- A hub script that modules call by path: rejected, it is a path to another module.
- A Python resolver in every module: rejected, the wrapper needs the path before Python starts.

## Consequences

- A standalone module finds a vendored `aicore` without the hub.
- A change of the fragment is a change of every carrier at once, checked by the test.

## Supersedes

None.
