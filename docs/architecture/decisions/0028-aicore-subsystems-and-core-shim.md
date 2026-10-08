# ADR 0028: aicore subsystems and the `core` compatibility shim

## Status

Accepted

## Context

The shared code lived in the flat root package `core/` and was imported by name from `skiller`, `harness`, `maind`,
`analyst`, `task` and hub scripts. Moving it into `aicore` must not break those consumers before their own stages,
and tests patch module paths such as `core.provider.lock.X`.

## Decision

The code moves with `git mv` into subsystems of `packages/aicore/lib/aicore/`: `util` (block, cli, env, http, io,
paths, proc, project, repo, term, text, digest, schema), `provider` (the provider model, errors, models),
`artifacts` (artifact, lock, reconcile) and `usage`. `aicore/__init__.py` is not a flat facade; code imports the
subpackages. Provider data ships in `packages/aicore/configs/` and is found from the package file, not from the
repository root. `core/__init__.py` stays as a shim: it makes `aicore` importable and registers each old module
name in `sys.modules` as the same object as the new one (`core.io is aicore.util.io`), and keeps the old flat
`__all__`. Modules that are not moved yet (`config_paths`, `gitignore_policy`, `runs`, `pathology`,
`codegraph_telemetry`) stay in `core/`. The window of the shim lasts until `core/` is removed with the hub modules'
move onto `aicore`; a test checks module identity and the facade.

## Alternatives considered

- A flat `aicore` with `from aicore.x import *` files in `core/`: rejected, star re-exports lose private names and
  break `mock.patch` by the old path.
- Rewrite every consumer import at once: rejected, it mixes the foundation move with the stages of seven modules.

## Consequences

- Consumers keep working; new code imports `aicore`.
- `core/` shrinks to the shim and the modules owned by later stages.

## Supersedes

None.
