# ADR 0073: swissknifeman doctor aggregates the doctor probes of modules, read-only

## Status

Accepted

## Context

[ADR 0022](0022-doctor-as-module-contract.md) made doctor a module contract and [ADR 0069](0069-module-doctor-contract.md)
made every module print `check-result/v1`. The umbrella `doctor` still ran `<cli> doctor` of four modules by name and
printed text.

## Decision

- **Source.** The checks are `provides.doctor` of each `unit.json`: `id`, `category`, `probe`. The aggregator runs every
  unique probe once, from the module root, with a timeout (`--timeout`, default 120 s), without input.
- **Validation.** Probe output must be `check-result/v1` documents. A probe that cannot start, times out, prints nothing or
  prints an invalid document gives one synthetic `fail` `<module>.doctor`; a declared id without a result gives a synthetic
  `fail` for that id. A probe's exit code is ignored when its output is valid.
- **Selection.** `--unit` (repeatable) and `--category`. Modules without doctor are listed, not failed.
- **Output.** Text lines, or `--json` as `umbrella-doctor/v1`. Exit 1 on any `fail`, 2 on a usage error.
- **No repair.** The aggregator only reads. Repair stays in the modules; the remediation text is printed.
- The earlier `doctor.fanout` key of `configs/umbrella.json` is removed.

## Alternatives considered

- Running `<cli> doctor` of each module: rejected, it needs the module's name and loses the per-check declaration.
- Aggregating repairs: rejected, repair needs a plan and a confirmation per module.

## Consequences

- A module joins the aggregate by declaring `provides.doctor`.
- A probe that writes state is a defect of the module, not of the aggregator.

## Supersedes

None. Extends ADR 0022 and ADR 0069.
