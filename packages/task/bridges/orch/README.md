# Bridge task ↔ orch

The only place where Task knows the orch execution contract `exec/v1`. The Task core stays neutral;
replacing the orchestrator means adding another bridge under `bridges/`, not editing the core.

| Verb | Entrypoint | Direction |
| --- | --- | --- |
| `brief` | `brief.py` | Task → orch: plan item or unit as an `execution-input` |

Run a verb through the Task dispatcher: `plan.py bridge orch <verb> [args…]`. `plan.py bridge list`
validates `bridge.json` and lists the verbs.

## brief

```text
plan.py bridge orch brief <plan> <item> [--unit U#] [--inline-reads] [--out FILE] [--repo NAME=PATH] [--plans-root DIR]
```

Returns the worker's `exec/v1` execution-input as JSON (`$schema`
`urn:swissknifeman:orch:exec:execution-input:v1`, `provenance.generated_by.tool` `task/bridges/orch brief`).

- It holds the task, scope, acceptance checks, constraints, reads with `sha256`, decisions and upstream
  results; completeness is checked without truncation (`BRIEF_INCOMPLETE` names each omission).
- Lifecycle instructions, the report API, the full plan and owner messages are excluded; the full
  coordinator pack stays reachable through `context_refs`.
- `--unit U#` briefs one unit: its goal, files (write set), checks and instructions. A unit without
  files is read-only with no write authority.
- `--inline-reads` embeds the full text of existing text reads; binary reads get `error`.
- Cross-plan decisions resolve in the current repository or through repeatable `--repo NAME=PATH` /
  `SKM_PLAN_REPOS`; an unresolved required decision refuses with `REF_UNRESOLVED`.
- Read refs become paths. A ref with no source path refuses with `REF_UNRESOLVED`, including optional
  reads; a declared optional artifact may still have an absent file (`exists: false`).
- `--out FILE` writes a file outside the plan directory (`OUT_INVALID` otherwise) and prints its path;
  without it the document goes to stdout. The verb never changes plan state.
- `digest` is sha256 of canonical JSON without `digest` and without the `@` suffix of `input_id`;
  `input_id` ends with `@<first 12 digest chars>`.

Exit codes: 0 ok, 1 refusal (stderr `CODE: message`), 2 usage. The dispatcher passes output and exit
code through unchanged, also under `plan.py --output json`.

## Finding orch

`brief` needs no orch: the bridge knows the format. orch is needed only for the conformance tests.
`partner.find_orch_root()` looks for a directory with `scripts/orch.py`:

1. `SKM_ORCH_ROOT`;
2. an `orch` command on `PATH` (its real path, two levels up);
3. the monorepo sibling `<Task root>/../orch`.

The bridge never imports orch; it calls `python3 <orch>/scripts/orch.py validate <kind> <file>`. When orch
is required and missing, `require_orch()` prints `BRIDGE_PARTNER_UNAVAILABLE: orch not found (set
SKM_ORCH_ROOT)` and exits 3. Check-evidence formats are described in orch's `docs/contracts.md`.

## Tests

```bash
cd packages/task
PYTHONPATH=lib python3 -m unittest discover -s bridges/orch/tests -t bridges/orch/tests -p 'test_*.py'
```

`test_brief.py` works without orch. `test_conformance.py` (documents valid for `orch.py validate`, lifecycle
phrases of the bridge ⊇ orch's) and `test_schema_profile.py` (orch's closed schema profile ⊇ Task's) skip
when orch is not found. `validate.sh` of Task runs these tests.
