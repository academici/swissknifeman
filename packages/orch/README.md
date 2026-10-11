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
Starting runs is future work; `prepare` without `--dry-run` returns `NOT_IMPLEMENTED`.
The launch catalog (`configs/launch-catalog.json`, `orch.py launch list|show|argv`) states how each role starts on
claude-code, codex and grok by model class, never by model; `argv` builds a command line and starts nothing.
The grok `reviewer` runs headless under `scripts/ro-run.py` (Linux Landlock): the filesystem stays readable,
writes go only to temp directories, `~/.grok` and `{cwd}/vendor`; `{orch}` in an argv is this package root.
Incompatible versions return `CONTRACT_VERSION` before schema validation.
The `[orch]` configuration (engine, per-role engine, default profile, work source, capability freshness, pack
folders, events) is layered through aicore; `orch.py --config FILE` adds the invocation layer. Run-policies ship as
versioned packs with test cases (`configs/run-policies/<id>/`): `orch.py policy list|show|test`.

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
- [adding-an-engine](docs/adding-an-engine.md)
