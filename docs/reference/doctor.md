# Doctor aggregator

`swissknifeman doctor` runs the read-only health checks that every module declares and prints them together
([ADR 0073](../architecture/decisions/0073-doctor-aggregator.md)). It does not repair: it prints the remediation of each
failed check.

```bash
swissknifeman doctor                       # every module
swissknifeman doctor --unit maind --unit harness
swissknifeman doctor --category config --json
```

## Options

| Option | Meaning |
| --- | --- |
| `--unit ID` | only this module; repeat for several; an unknown id is `UNIT_UNKNOWN` (exit 2) |
| `--category C` | only checks of the category: `environment`, `config`, `state`, `content`, `integration` |
| `--timeout S` | seconds per probe, default 120 |
| `--json` | print `umbrella-doctor/v1` |

## What runs

A module declares checks in `provides.doctor` of its `unit.json`: `id`, `category` and `probe`, an argv relative to the
module root. Several checks may share one probe (maind declares six checks behind `bin/maind doctor --json`). The
aggregator runs each unique probe once, from the module root, with a timeout. The probe prints `check-result/v1`
documents; each one is validated against the schema.

A synthetic `fail` is reported when

- a probe cannot start, times out, prints nothing or prints something that is not valid `check-result/v1`
  (one `<module>.doctor` result for the probe), or
- a declared check id has no result in the output of its probe.

The exit code of a probe is ignored when it printed valid documents. Modules without `provides.doctor` are listed
under `units_without_doctor`.

## Output

Text: one `<status> <check_id>: <observed>` line per result, a count line, then the remediation of every `warn` and
`fail`. Exit code 1 when any result is `fail`, 0 otherwise, 2 for a usage error.

`--json`:

```json
{
  "schema": "umbrella-doctor/v1",
  "results": [
    {"$schema": "urn:swissknifeman:aicore:check-result:v1", "check_id": "harness.hooks", "status": "ok",
     "category": "integration", "observed": "...", "unit": "harness"}
  ],
  "units_without_doctor": ["planner"]
}
```

The schema is `configs/schemas/umbrella-doctor.schema.json`; each result is a `check-result/v1` document plus `unit`.

## Repair

Probes only read. Repair stays in the module: split into plan and apply as in
[ADR 0069](../architecture/decisions/0069-module-doctor-contract.md) (for example `maind health --plan-repair`).
