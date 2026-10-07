# Bridge task ↔ orch

The only place where Task knows the orch execution contract `exec/v1`. The Task core stays neutral;
replacing the orchestrator means adding another bridge under `bridges/`, not editing the core.

| Verb | Entrypoint | Direction |
| --- | --- | --- |
| `brief` | `brief.py` | Task → orch: plan item or unit as an `execution-input` |
| `register` | `register.py` | orch → Task: a worker's stage-report into `log` + `finish` or `unit … return` |
| `register-review` | `register_review.py` | orch → Task: review-findings into `add-document` + a `note` event |
| `commit` | `commit.py` | Task → orch: one scoped operation commit as a stage-result `commits[]` fragment |
| `launch` | `launch.py` | orch → Task: a role's launch command line with the model resolved from Task's provider mapping |

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

## register

```text
plan.py bridge orch register <plan> <item>[/<U#>] --report REPORT.json --status STATUS --actor P/M[/E]
        [--executed-by P/M[/E]] [--attempt-id ID] [--evidence V#=PATH …] [--plans-root DIR] [--dry-run]
```

The orch registrar role classifies the report and hands it here; the bridge maps every field into the plan
and writes **only** through `plan.py` (`TASK_PLAN_PY`, a subprocess), never into plan files.
Never manufacture evidence: a check that did not run is not in `checks_run`, and the bridge invents no exit
or verdict.

REPORT.json is the executor's stage-report (`result_contract.report`), closed — an unknown field is refused
so nothing is lost:

```text
{summary: str, changed_paths: [str], checks_run: [{id: V#, cmd, exit: int} | {id: V#, procedure, verdict: pass|fail}],
 evidence: [path], open_issues: [{text, kind: pending|deviation|blocker|difficulty|assumption|note|escalation, impact?, next?}]}
```

| Report field | Plan call (item) |
| --- | --- |
| `summary` + `changed_paths` | `finish … --notes "<summary>\nChanged: a, b"` |
| `checks_run` entry without evidence | `--check V#=<exit>` (`verdict` pass → 0, fail → 1) |
| `--evidence V#=PATH` argument | `--evidence V#=PATH`; the evidence file carries the exit, so no `--check` for that check |
| `evidence` path without a `--evidence` argument | named in `--notes` (`Evidence: …`) |
| issue `pending` | `--pending <text>` |
| issue `deviation` | `log <plan> <item> --type deviation --summary <text> [--impact] [--next]` and `--deviation <text>` (needs `--status done_with_deviations`) |
| issue `blocker`, `difficulty`, `assumption`, `note` | friction: `log <plan> <item> --type <kind> --summary <text> [--impact] [--next]` |
| issue `escalation` | `--escalation <text>` (needs `--status blocked`; several are joined with `; `) |
| worker, registrar, delivery | `--executed-by`, `--actor`, `--attempt-id` on `finish`; `--actor` on each `log` |

A unit (`<item>/<U#>`) ends with `unit <plan> <item> <U#> return --notes <summary> --changed <path>…
[--executed-by] [--attempt-id]`. Checks and evidence are named in its notes: the integrator records them with
`unit … accept|rework|reject` (`accept --evidence V#=PATH`), and the bridge prints that hint. Issues become
`log` events (`pending` as a `note` prefixed `pending: `); an escalation and any `--status` other than `done`
are refused for a unit.

Order: every `log`, then one `finish` or `return`. Idempotency: a repeat with the same `--attempt-id` is a
no-op in the core for `finish` and `return`; `log` is not deduplicated by the core, so a report with
`open_issues` needs `--attempt-id`, and before writing the bridge reads `plan.py --output json events <plan>
--item <item> --type <types>` and skips a `log` whose `type` and `summary` the item already has.

`--dry-run` prints the JSON list of `plan.py` argv and writes nothing. Otherwise stdout is the
registration-receipt `{"plan", "ref", "calls": [{"argv", "exit", "result": "recorded|no-op|refused",
"error"?}], "next"}`, where `next` is the `plan.py next <plan>` line. The first refused call stops the
registration (exit 1, receipt without `next`); a repeat with the same attempt id completes it.

## register-review

```text
plan.py bridge orch register-review <plan> <item|phase> --findings FINDINGS.json --actor P/M[/E] [--plans-root DIR] [--dry-run]
```

FINDINGS.json: `{verdict: GREEN|ATTENTION|RED, reviewer: {route, session}, findings: [{severity, confidence,
location, failure_scenario, basis}], date: YYYY-MM-DD}`. The bridge records

1. `add-document <plan> --json <doc>`: knowledge `review-<ref with . and / as ->-<date>`, title
   `Review <ref> <date>`, `applies_to: [<ref>]`, sections `verdict` and `findings` (the findings as JSON). The
   document travels as `--json` text, so no temporary file appears next to the plan;
2. `log <plan> <ref> --type note --summary "review <verdict>: @plan/knowledge/<id>.json; reviewer <route>
   session <session>"` — the actual reviewer route and session, not the requested one.

A repeat is a no-op: an identical stored document and a note already in the journal are skipped.

## commit

`plan.py bridge orch commit <plan> <item>[/<U#>] --role executor|reviewer|fix [options of plan.py commit]`

Runs `plan.py commit <plan> <ref> … --json` as a subprocess (the bridge calls Task through its CLI, as
`register` does; nothing is imported) and prints the fragment for a stage-result:

```json
{"commits": [{"sha": "…", "role": "executor", "ref": "P1.1", "paths_digest": "<sha256>"}]}
```

`paths_digest` is the Task result's digest of the sorted repo-relative paths; orch computes the same value
independently (`\n`-joined, no trailing newline). Every argument after `<plan> <ref>` is passed to `plan.py
commit` unchanged. A refusal of Task (`OUTSIDE_SCOPE`, `NOTHING_TO_COMMIT`, …) is printed as `CODE: message`
on stderr, exit 1. A `--dry-run` creates no commit, so the bridge refuses with `COMMIT_RESULT_INVALID`.

## Refusals of register and register-review

Bridge codes (stderr `CODE: message`, exit 1, nothing written): `REGISTER_REPORT_INVALID`,
`REGISTER_UNCLASSIFIED` (an `open_issues` entry without a known `kind` — classify, never guess),
`REGISTER_STATUS_MISMATCH`, `REGISTER_ATTEMPT_REQUIRED`, `REGISTER_FINDINGS_INVALID`. They are bridge codes,
not core `ERROR_CODES`. A refusal of a `plan.py` call (`CODE: message` of the core) lands in the receipt as
`refused` with its `error`.

## Finding orch

`brief` needs no orch: the bridge knows the format. orch is needed only for the conformance tests.
`partner.find_orch_root()` looks for a directory with `scripts/orch.py`:

1. `SKM_ORCH_ROOT`;
2. an `orch` command on `PATH` (its real path, two levels up);
3. the monorepo sibling `<Task root>/../orch`.

The bridge never imports orch; it calls `python3 <orch>/scripts/orch.py validate <kind> <file>`. When orch
is required and missing, `require_orch()` prints `BRIDGE_PARTNER_UNAVAILABLE: orch not found (set
SKM_ORCH_ROOT)` and exits 3. Check-evidence: the Task core checks its own field contract
(`plan.py schema check-evidence`) with any `$schema`, so exec/v1 check-evidence passes unconverted;
`test_conformance.py` proves it on orch's fixtures.

## Tests

```bash
cd packages/task
PYTHONPATH=lib python3 -m unittest discover -s bridges/orch/tests -t bridges/orch/tests -p 'test_*.py'
```

`test_brief.py`, `test_register.py` and `test_commit_bridge.py` (the stage-result check skips without orch) work without orch. `test_conformance.py` (documents valid for
`orch.py validate`, lifecycle phrases of the bridge ⊇ orch's, orch check-evidence accepted by Task) and
`test_schema_profile.py` (orch's closed schema profile ⊇ Task's) skip when orch is not found.
`test_record_parity.py` pins every recording obligation W1–W12 to its owner; rows owned by orch roles or by
this repository's plan skip when those are absent. `validate.sh` of Task runs these tests.

## launch

```text
plan.py bridge orch launch <role> <provider> [--model M] [--effort E] [--cwd DIR] [--routing FILE]
```

Prints `{argv, transport, timeout_s, model, model_class}` and starts nothing. The entry comes from the partner's
launch catalog (`orch.py launch show|argv`); the catalog holds a `model_class`, never a model. The bridge maps the
class to a model through `mappings.<provider>.class_selectors` in `configs/command-routing.json` (`--routing`
overrides the file) and the effort through `effort_selectors`. `--model` pins the exact model of an owner
selector (`reviewer grok/grok-4.7`) instead of the class mapping. Providers whose CLI takes no model
(`model_set: unknown`, grok `executor`) get no model argument; `--model` there is `LAUNCH_INVALID`. Refusals: `LAUNCH_UNKNOWN` (no entry),
`LAUNCH_INVALID` (bad request or catalog), `LAUNCH_MODEL_UNRESOLVED` (mapping has no model for the class),
`ROUTING_UNREADABLE`.

A reviewer on another provider (`reviewer-selection`): `plan.py bridge orch launch reviewer grok --model grok-4.7
--effort high --cwd <repository>`. The grok entry runs headless under orch `scripts/ro-run.py` (Linux Landlock, no
root, no user namespaces): the filesystem stays readable, writes go only to temp directories, `~/.grok` and
`<repository>/vendor` (test caches); the brief goes on stdin (`--prompt-file /dev/stdin`), the stream is
`streaming-messages-json` under `bypassPermissions` with the edit tools disallowed. The tests also compare the argv of `scout` with Task's own `orchestration.scout`, which
`start --scout` keeps using unchanged.
