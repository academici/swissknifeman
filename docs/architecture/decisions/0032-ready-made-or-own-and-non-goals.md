# ADR 0032: Ready-made or own: criteria, non-goals, Python 3.9

## Status

Accepted

## Context

An external review proposed many ready-made solutions (model gateways, workflow engines, policy engines, plugin
frameworks, observability platforms). Modules are stdlib-only and installed without pip. The minimum Python version
was stated three ways: 3.8 in `doctor`, 3.9 in the item rules, 3.11 in the TOML decision.

## Decision

A candidate is checked with five questions: is there a consumer now; does it need pip, a server or a daemon at
runtime; does it run on Python 3.9; does it carry foreign types or state into our contracts; can it be replaced
behind a port. The outcomes are: a **format or protocol** (JSON Schema, CloudEvents fields, MCP, TOML, XDG,
OpenTelemetry names) is adopted as a format with a stdlib implementation; a **library** only when needed now and
small, vendored into `aicore/_vendor` with licence, pinned version and a check against the original source, or an
optional dev dependency that tests skip when absent; a **server or framework** stays out of the core and out of
contracts, and may come only as an optional adapter behind a port on a recorded trigger; a **pattern** (journal
first, cursor, tools snapshot, structured policy decision) is taken as an idea and implemented minimally.

Non-goals: the orch engines are not a durable runtime (timers, signals, replay, compensation, multi-day runs); MCP is
a tool surface, not the event bus `aicore.ext`, not the source of truth about a run and not a replacement of
contracts; a model gateway, if one appears, does not own run state. The minimum is Python 3.9; TOML is read with
`tomllib` on 3.11 and later and otherwise with a vendored reader.

## Alternatives considered

- Adopt the suggested stack as dependencies: rejected, it breaks stdlib-only delivery.
- Write everything ourselves: rejected, formats and protocols are cheaper to adopt.

## Consequences

- Every "use X" proposal has a fixed test and a recorded outcome.
- Doctor thresholds are brought to 3.9 in the stage of each module.

## Supersedes

Narrows the TOML reading statement of [ADR 0011](0011-toml-for-human-edited-config.md) (3.9 minimum, vendored reader).
