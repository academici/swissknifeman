# ADR 0022: Doctor is a contract of every module

## Status

Accepted

## Context

Each module has its own `doctor` with its own output shape.

## Decision

A module declares checks in `unit.json` (`provides.doctor`): id, category and a read-only probe command. A check
result follows the `check-result` schema (`status`, `category`, `observed`, `evidence`, `remediation`). Repair is
separate: probe, plan-repair, apply-repair (with confirmation), verify-repair. `swissknifeman doctor` aggregates
module checks discovered from `unit.json`; modules convert their `doctor` output to `check-result` in the hub-module
stage, where `maind health --fix` is split into probe and repair.

## Alternatives considered

- Keep module-specific doctors: rejected, no aggregation is possible.

## Consequences

- The schema and the manifest field exist now; the conversion and aggregation happen later.
- Probes must be read-only, which the module check can verify.

## Supersedes

None.
