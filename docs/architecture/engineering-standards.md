# Engineering standards

[ADR 0012](../adr/0012-dependency-policy.md) and [dependencies](../dependencies.md)
bound third-party libraries. Generated DTOs come only from `make gen`. Executor
validation is separate from review, and a change does not require its own commit.

## Code and dependencies

Python 3.12+ uses src layout, uv with a frozen lock, Ruff and Pyright. Prefer pure
functions; immutable values use frozen dataclasses and tuples. IO implementations
sit behind Protocols and explicit constructor dependencies. No mutable global
registries, service locators or import-time registration. Files group one coherent
responsibility; grab-bag names are forbidden. Size thresholds guide splitting;
architecture checks warn above 600 lines and reject above 900 outside generated code.

Domain code has no IO, clock or environment. Time and IDs are injected. Boundary
DTOs come from JSON Schema and code generation; generated types are never
handwritten. No additional runtime libraries without the [dependency policy](../dependencies.md).
Subprocesses use argument lists, bounded output/time and explicit environments;
SQL is parameterized. Path operations check containment and symlink escapes.
Errors cross module boundaries as cataloged `SkmError` values; cleanup preserves
the primary failure. Logs are structured and redact secret references/content.

## Test pyramid

| Level | Location | Proof |
|---|---|---|
| Domain | `tests/unit/` | Invariants and transitions without IO |
| Application | `tests/unit/` | Handlers with memory UoW |
| Contract | `tests/contracts/` | Shared port suites for memory and PostgreSQL |
| Integration | `tests/integration/` | SQL, Git, process and adapter boundaries |
| Recovery | `tests/recovery/` | Faults before/after commit, lease loss and unknown effects |
| Security | `tests/security/` | Scope, tokens, permissions, symlinks and stale claims |
| Architecture | `tests/architecture/` | AST import/ownership rules and deliberate bad fixtures |
| E2E | `tests/e2e/` | Scenarios through real surfaces with fake runtimes |
| Live evals | `tests/evals/` | Explicit opt-in, bounded paid provider verification |

Tests use deterministic clocks/IDs, isolated resources and behavioral assertions.
New checker rules need negative regressions in the default-collected root `tests/`
tree. New tests must fit the assigned write scope. A skipped/unavailable check is
not green evidence.

## Checks

`make check` runs `fmt-check lint typecheck test arch docs-check schema-check`;
`make check-touched` is the targeted preflight for a diff. CI runs the same checks as
sharded lanes; see [Continuous integration](../guides/continuous-integration.md).
`docs-check` runs `python tools/check_links.py docs README.md` through frozen uv.
It recursively checks Markdown local destinations and heading anchors, reporting
`path:line: broken link target` with exit 1. HTTP/mail and other URI schemes do not
trigger network requests. Unavailable tools print `skip:` and fail; no placeholder
target enters `check`. PostgreSQL, E2E, eval and performance targets remain real
pytest selections and fail when no tests are collected.

## Documentation and work records

README and new living docs are English. Architecture pages are the living architecture;
ADR statuses remain explicit. The contract inventory is maintained independently.
Generated references follow their generators.
[Status](../status.md) records executor commands/results separately from reviewed/by/outcome.
[Porting records](../porting-log.md) retain provenance names and preserved guarantees.
Manual work has no mandatory JSON report, automatic reviewer or per-leaf commit;
explicit owner/campaign instructions still govern the active execution mode.
