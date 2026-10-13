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
`conduct.py run --plan P --items REF…|--batch` claims pieces of work through the work source and drives each one through
context, scout, executor, checks, review, triage, correction, registration and commit until green or an honest stop,
with progress lines on stderr, `resume` without repeating closed steps and an observer report
([docs/conductor.md](docs/conductor.md)). `orch.py doctor` checks that git ignores the conductor's runtime files.
The launch catalog (`configs/launch-catalog.json`, `orch.py launch list|show|argv`) states how each role starts on
claude-code, codex and grok by model class, never by model; `argv` builds a command line and starts nothing.
The grok `reviewer` runs headless under `scripts/ro-run.py` (Linux Landlock): the filesystem stays readable,
writes go only to temp directories, `~/.grok` and `{cwd}/vendor`; `{orch}` in an argv is this package root.
The claude-code `executor`, `bounded-implementer` and `triager` run under it too (shell allowed with `--allowedTools Bash`; the
executor and the bounded-implementer write only to `{cwd}`, the triager nowhere), and the `registrar` may run only
`python3 *orch.py source register *`. Every headless claude-code role starts with `--permission-prompts none` (what would ask
is denied, nobody answers) and never with `--bare`, which does not read the subscription login.
Incompatible versions return `CONTRACT_VERSION` before schema validation.
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
- [conformance](docs/conformance.md)
- [events](docs/events.md)
- [adding-an-engine](docs/adding-an-engine.md)
