# orch

Internal, engine-neutral orchestration contracts for the swissknifeman monorepo.
Status: **internal, not published (decision D2 of the orchestration-prep plan)**. Runtime code uses only the Python
standard library and `orch`; it is independent of other packages of this repository.

The package supplies a closed-profile JSON Schema validator, shared `exec/v1`
definitions, all nine document schemas and their fixtures, canonical document
digests and a `validate` CLI. It also defines the EnginePort protocol, RunState
reducer and binding capability matrix. `orch.py prepare --binding native|cao|claude-only --provider P --input I
--policy POLICY --out DIR --dry-run` prints a launch-plan and writes its prompt or CAO profile files into `DIR`;
models come from the `mappings` of a routing config (`--routing`, `ORCH_ROUTING` or a bridge's `routing_path()`).
Starting runs is future work; `prepare` without `--dry-run` returns `NOT_IMPLEMENTED`.
The launch catalog (`configs/launch-catalog.json`, `orch.py launch list|show|argv`) states how each role starts on
claude-code, codex and grok by model class, never by model; `argv` builds a command line and starts nothing.
The grok `reviewer` runs headless under `scripts/ro-run.py` (Linux Landlock): the filesystem stays readable,
writes go only to temp directories, `~/.grok` and `{cwd}/vendor`; `{orch}` in an argv is this package root.
Incompatible versions return `CONTRACT_VERSION` before schema validation.

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

The registry rejects schema keywords outside its closed profile. Its validator
is an adapted copy of the plan store's closed-profile validator (decision D4 of the orchestration-prep plan);
the plan bridge tests keyword parity.

## Docs

- [index](docs/index.md)
- [contracts](docs/contracts.md)
- [engine-port](docs/engine-port.md)
- [architecture](docs/architecture.md)
- [adding-an-engine](docs/adding-an-engine.md)
