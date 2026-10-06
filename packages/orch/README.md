# orch

Internal, engine-neutral orchestration contracts for the swissknifeman monorepo.
Status: **internal, not published (PLAN2.D2)**. Runtime code uses only the Python
standard library and `orch`; it is independent of other packages of this repository.

The package supplies a closed-profile JSON Schema validator, shared `exec/v1`
definitions, all nine document schemas and their fixtures, canonical document
digests and a `validate` CLI. It also defines the EnginePort protocol, RunState
reducer and binding capability matrix; execution bindings are future work.
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
is an adapted copy of the plan store's closed-profile validator (PLAN2.D4);
the plan bridge tests keyword parity.
