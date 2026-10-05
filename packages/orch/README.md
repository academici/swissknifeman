# orch

Internal, engine-neutral orchestration contracts for the swissknifeman monorepo.
Status: **internal, not published (PLAN2.D2)**. Runtime code uses only the Python
standard library and `orch`; it is independent of Task, Skiller, Harness and core.

The initial skeleton supplies a closed-profile JSON Schema validator, the shared
`exec/v1` definitions, canonical document digests and a `validate` CLI. The nine
document schemas and their fixtures are added in PLAN2.P1.2 and PLAN2.P1.3; until
then, validating a document with a compatible version reports an unavailable
schema. Incompatible versions return `CONTRACT_VERSION` before schema validation.
The semantic dispatcher is ready for the checks supplied with those schemas.

From the repository root:

```bash
python3 packages/orch/scripts/orch.py validate <kind> <file.json> [--quiet]
bash packages/orch/scripts/test.sh -v
bash packages/orch/scripts/validate.sh
```

`validate` prints `{"valid": true}` on success or a JSON list of
`path`, `code` and `message` issues on failure. Diagnostics use `CODE: message`
on stderr. Exit codes: `0` success, `1` invalid input or refusal, `2` usage error.
`--quiet` suppresses stdout and preserves diagnostics and the exit status.

The registry rejects schema keywords outside its closed profile. Its validator
is an adapted copy of `task/plan/schema.py` (PLAN2.D4); tests compare the supported
keywords and error codes by reading Task's source, without importing Task.
