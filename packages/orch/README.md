# orch

Internal, engine-neutral orchestration contracts for the swissknifeman monorepo.
Status: **internal, not published (decision D2 of the orchestration-prep plan)**. Runtime code uses only the Python
standard library, `orch` and the `aicore` foundation (schema validator, digest, model catalog); it is independent
of every other package of this repository. The aicore checkout is found through `AICORE_ROOT`, `_vendor/aicore` or
the sibling `aicore` folder.

The package supplies the `exec/v1` schemas validated by the closed-profile validator of aicore, shared `exec/v1`
definitions, all nine document schemas and their fixtures, canonical document
digests and a `validate` CLI. It also defines the EnginePort protocol, RunState
reducer and binding capability matrix. `orch.py prepare [--binding native|cao|claude-only] --provider P --input I
--policy POLICY --out DIR --dry-run` prints a launch-plan and writes its prompt or CAO profile files into `DIR`; without
`--binding` the `[orch]` configuration chooses the engine. The launch-plan records the digests of every input, the
configuration it was prepared with, the route and engine decisions with the candidates considered, the policy decision
and the proof of the capability records; `orch.py explain LAUNCH_PLAN [--json]` reads it back without writing anything.
Models come from the `model-catalog/v1` file of aicore (`--model-catalog FILE`; the default is the catalog packaged with aicore).
`prepare` without `--dry-run` returns `NOT_IMPLEMENTED`; runs are started by the conductor:
`orch conduct run --plan P --items REF…|--batch` claims pieces of work through the work source and drives each one through
context, scout, executor, checks, review, triage, correction, registration and commit until green or an honest stop,
with progress lines on stderr, `resume` without repeating closed steps and an observer report
([docs/conductor.md](docs/conductor.md)). `orch.py doctor` checks that git ignores the conductor's runtime files.
The launch catalog (`configs/launch-catalog.json`, `orch.py launch list|show|argv`) states how each role starts on
claude-code, codex and grok by model class, never by model; `argv` builds a command line and starts nothing.
Grok's `executor`, `bounded-implementer`, `reviewer`, `triager`, `researcher`, `advisor` and `report-fixer` entries use jsonl
(`streaming-messages-json`); `scout` uses text (`--output-format plain`) with web search disabled. All run under
`scripts/ro-run.py` (Linux Landlock). Writers grant `--rw {cwd}`; the reviewer and triager
use `--protect {cwd} --rw {cwd}/vendor`, and the scout, researcher, advisor and report-fixer use `--protect {cwd}`. Protected roles require
Landlock ABI >= 3 and refuse a checkout inside `/tmp`, `/var/tmp`, `/dev` or `~/.grok`, or a symlink/escaping
in-checkout writable grant. Read-only roles restrict Grok's edit and delegation tools; the report-fixer also disables shell.
The filesystem stays readable, with default writes to temporary directories, `/dev` and `~/.grok`.
Preflight checks the provider after the wrapper's `--`, so a missing Grok CLI is unavailable in `--dry-run`.
ACP routes remain unsupported by the conductor. `{orch}` in an argv is this package root.
The claude-code `executor`, `bounded-implementer` and `triager` run under it too (shell allowed with `--allowedTools Bash`; the
executor and the bounded-implementer write only to `{cwd}` and the temporary directories, the triager only to the
temporary directories), and the `registrar` may run only
`python3 *orch.py source register *`. Every headless claude-code role starts with `--permission-prompts none` (what would ask
is denied, nobody answers) and never with `--bare`, which does not read the subscription login.
Incompatible versions return `CONTRACT_VERSION` before schema validation.

## Role/provider matrix

Every role/provider pair has a launch entry or an explicit refusal:

| Role | claude-code | codex | grok |
| --- | --- | --- | --- |
| scout | ✓ | ✓ | ✓ |
| executor | ✓ | ✓ | ✓ |
| bounded-implementer | ✓ | ✓ | ✓ |
| reviewer | ✓ | ✓ | ✓ |
| triager | ✓ | ✓ | ✓ |
| registrar | ✓ | ✓ | refused: plan writes outside checkout |
| report-fixer | ✓ | ✓ | ✓ |
| researcher | ✓ | refused: read-only has no network | ✓ |
| advisor | ✓ | refused: read-only has no network | ✓ |

The optional catalog key `refusals` holds the reasons. A refused pair returns
`LAUNCH_REFUSED: <role>/<provider>: <reason>`; an unlisted pair still returns `LAUNCH_UNKNOWN`.
Required roles stop before work; optional scout/report-fixer roles are skipped. Dry-run lists the reason in
`unavailable`, and `route explain` and the planner bridge retain the same code. The existing registrar.codex
`workspace-write` entry is the explicit exception to read-only sandbox checks. Researcher/advisor Grok retain shell
and network access to research sources; Landlock confines source writes to its writable areas.

The `[orch]` configuration (engine, per-role engine, default profile, work source, capability freshness, pack
folders, events) is layered through aicore; `orch.py --config FILE` adds the invocation layer. Run-policies ship as
versioned packs with test cases (`configs/run-policies/<id>/`): `orch.py policy list|show|test`.
Work comes from the extension point `orch:work-source` (contract `schemas/work-source/v1`), served by the plugin
named by `work_source`: `orch.py source claim|brief|prepare|register|commit` claims an item for a run, stores its brief as
an artifact, writes the run's `launch-plan.json`, registers the outcome through owner fencing and an evidence gate and
commits it
([docs/work-source.md](docs/work-source.md)).

Bridges to the partners live in the hub (`bridges/`, see its README), not in this package. `orch` does not run durable
timers, signals, workflow replay, compensation or multi-day executions, and MCP is not its event bus
([architecture](docs/architecture.md#non-goals)). Engine scenarios are compared with `orch.py conformance`
([docs/conformance.md](docs/conformance.md)); the `orch.run.*` events are in [docs/events.md](docs/events.md).

From the repository root:

```bash
python3 packages/orch/scripts/orch.py validate <kind> <file.json> [--quiet]
bash packages/orch/scripts/test.sh -v
bash packages/orch/scripts/validate.sh
```

`validate` prints `{"valid": true}` on success or a JSON list of
`path`, `code`, `message` and `level` issues when diagnostics are present.
Diagnostics use `CODE: message` on stderr. Exit codes: `0` success (including
warning-only documents), `1` invalid input or refusal, `2` usage error.
`--quiet` suppresses stdout and preserves diagnostics and the exit status.

The registry rejects schema keywords outside its closed profile. The validator is the closed-profile validator
of aicore (`orch.schema` re-exports it); `tests/test_schema_profile.py` checks that orch keeps no profile of its own.

## Docs

- [index](docs/index.md)
- [configuration](docs/configuration.md)
- [run-policies](docs/run-policies.md)
- [contracts](docs/contracts.md)
- [engine-port](docs/engine-port.md)
- [architecture](docs/architecture.md)
- [work-source](docs/work-source.md)
- [conductor](docs/conductor.md)
- [Role/provider matrix](#roleprovider-matrix) — launch entries and explicit refusals.
- [Ownership of a run](docs/conductor.md#ownership-of-a-run) — leases, one conductor per checkout and orphaned runs.
- [Recovery after a crash](docs/conductor.md#recovery-after-a-crash) — interrupted steps, receipts and local durability.
- [Token usage and limits](docs/conductor.md#hard-token-limits-and-resume) — accounted fresh tokens, incomplete usage, hard limits and limit raises on resume.
- [Stubs variants](docs/conductor.md#stubs-additional-instructions-of-the-roles) — provider/model-family instructions and frozen snapshots.
- [gui-orch README](../../bridges/gui-orch/README.md) — used/available routes, prompt metadata, budget, gates and owner/orphaned views.
- [Deferred audit proposals](../../roadmap/2026-10-19-audit-deferred.md) — measurable triggers, module owners and audit sources.
- [conformance](docs/conformance.md)
- [events](docs/events.md)
- [adding-an-engine](docs/adding-an-engine.md)
