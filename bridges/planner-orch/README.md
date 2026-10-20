# Bridge planner ↔ orch (`planner-orch`)

The only place where the planner knows the orch execution contract `exec/v1`. The planner core stays neutral;
replacing the orchestrator means adding another bridge under `bridges/`, not editing the core. The bridge is a unit
of the hub (`unit.json`, kind `bridge`); the planner finds it through `bridges.roots` of its configuration.

| Verb | Entrypoint | Direction |
| --- | --- | --- |
| `brief` | `brief.py` | Task → orch: plan item or unit as an `execution-input` |
| `register` | `register.py` | orch → Task: a worker's stage-report into `log` + `finish` or `unit … return` |
| `register-review` | `register_review.py` | orch → Task: review-findings into `add-document` + a `note` event |
| `commit` | `commit.py` | Task → orch: one scoped operation commit as a stage-result `commits[]` fragment |
| `launch` | `launch.py` | orch → Task: a role's launch command line with the model resolved from Task's provider mapping |

The bridge is also the plugin of orch's extension point `orch:work-source` (`extension.json`, entrypoint
`worksource.py`, `unit.json` `provides.ports`): see [Work source](#work-source).

Run a verb through the Task dispatcher: `plan.py bridge planner-orch <verb> [args…]`. `plan.py bridge list`
validates `bridge.json` and lists the verbs.

## brief

```text
plan.py bridge planner-orch brief <plan> <item> [--unit U#] [--inline-reads] [--out FILE] [--repo NAME=PATH] [--plans-root DIR]
```

Returns the worker's `exec/v1` execution-input as JSON (`$schema`
`urn:swissknifeman:orch:exec:execution-input:v1`, `provenance.generated_by.tool` `planner-orch brief`).

- It holds the task, scope, acceptance checks, constraints, reads with `sha256`, decisions and upstream
  results; completeness is checked without truncation (`BRIEF_INCOMPLETE` names each omission).
- Required reads are checked at the first claim only, as `plan.py start` does: the brief of an item already in progress
  (a repeated claim, `run --adopt`) does not refuse with `READ_MISSING` for a required file the item itself deleted
  (a workflow it retires); `exists: false` marks such a read.
- Lifecycle instructions, the report API, the full plan and owner messages are excluded: a text that tells the executor to run
  `plan.py start|finish`, `unit return` or `planner:plan-run` (a run word before it, a shell prompt, a code fence) refuses the
  brief with `BRIEF_INCOMPLETE`, while a text that only names them to describe a gate ("before `plan.py finish` the checks are
  green", "never run `plan.py finish`") passes; the report API is refused wherever it is named; the full
  coordinator pack stays reachable through `context_refs`.
- `research` carries the research need the designer set on the item: `rag.need` (`none`, `optional`, `required`) and `rag.notes`; `rag.status` and `rag.captures` are plan state and stay out. An item without `rag` gets no `research` field. Under `orch.research.policy = conditional` the conductor adds a research stage only for `required`.
- The review of the item: `review_mode` = `review.mode`; `review_route` = `review.reviewer` without its `note`
  ({class, provider, model, effort}, only the fields set); `review_rounds_max` = `review.rounds_max`. Each is present only
  when the plan sets it. The conductor reviews on `review_route` when the run sets no reviewer of its own (configuration,
  `orchestration.options.reviewer`, `--options`) and never runs more than `review_rounds_max` rounds. `review.covers` is a
  declaration for people and checkpoints and is not carried: the conductor does not execute it.
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
plan.py bridge planner-orch register <plan> <item>[/<U#>] --report REPORT.json --status STATUS --actor P/M[/E]
        [--executed-by P/M[/E]] [--attempt-id ID] [--evidence V#=PATH …] [--owner-session SESSION]
        [--gate evidence] [--plans-root DIR] [--dry-run]
```

The orch registrar role classifies the report and hands it here; the bridge maps every field into the plan
and writes **only** through `plan.py` (`PLANNER_PLAN_PY`, a subprocess), never into plan files.
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

Guards, both checked before the first call that changes the plan (the work-source port always passes both; without
them the registration behaves as described above):

- `--owner-session SESSION` (fencing): `plan.py --output json get <plan> <item>` must show
  `result.executor.session` = SESSION, or `result.attempt_id` = `--attempt-id` (the item was already closed by this
  attempt, so its repeat reaches `finish` and is a no-op there); otherwise `REGISTER_STALE_OWNER`, for example after
  `start --take-over` by another session. `finish` also gets `--owner-session SESSION`, so a take-over between this
  read and the closing write is refused by the planner under its plan lock (`ITEM_OWNED`, reported as
  `REGISTER_STALE_OWNER` with gate `stale`); `log` calls made in that window stay in the journal.
- `--gate evidence`: `done` and `done_with_deviations` need `--evidence` for every acceptance check of the item
  (`REGISTER_EVIDENCE_MISSING`, also for a file that the planner's `finish` would refuse: the gate reads it with the
  planner's own `load_evidence`, so `$schema`, subject, candidate and producer are checked) with exit 0 (a procedure:
  verdict `pass`; `REGISTER_EVIDENCE_RED` otherwise). Paths resolve as the planner resolves them
  (repository-relative or `@plan/`). `checks_run` entries without a file never become `--check`. `blocked` passes
  without evidence; a unit return has no gate (verdict `none`).

With a guard the receipt carries `"gate": {"verdict": "pass|missing|red|stale|none", "checks": {"V<n>": exit|null}}`;
a guard refusal prints the receipt with `calls: []` and that gate on stdout and `CODE: message` on stderr (exit 1).

## register-review

```text
plan.py bridge planner-orch register-review <plan> <item|phase> --findings FINDINGS.json --actor P/M[/E] [--plans-root DIR] [--dry-run]
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

`plan.py bridge planner-orch commit <plan> <item>[/<U#>] --role executor|reviewer|fix [options of plan.py commit]`

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
`REGISTER_STATUS_MISMATCH`, `REGISTER_ATTEMPT_REQUIRED`, `REGISTER_FINDINGS_INVALID`, and the guard codes
`REGISTER_STALE_OWNER`, `REGISTER_EVIDENCE_MISSING`, `REGISTER_EVIDENCE_RED`, `REGISTER_ITEM_UNREADABLE` (the item
cannot be read for a guard). They are bridge codes,
not core `ERROR_CODES`. A refusal of a `plan.py` call (`CODE: message` of the core) lands in the receipt as
`refused` with its `error`.

## Agent mode

The procedure of an agent that picks its own pieces (`packages/orch/docs/agent-mode.md`) starts with

```text
python3 <planner>/scripts/plan.py next <plan> --parallel N --json
```

The output is pinned by the golden file `packages/planner/tests/engine/fixtures/next-parallel-2.json`
(`tests/engine/test_next_golden.py` of the planner; `UPDATE_GOLDEN=1` regenerates it, then fix this section):

| Field | Meaning |
| --- | --- |
| `lanes[]` | work that may start now: `lane` (`L1`…), `kind` (`run-items` or `design-phase`), `phase`, `batch`, `items`, `route` (`class`, `effort`: the minimum of the work), `command`, `launch` (`claude`, `codex` command lines) |
| `running[]` | items in progress: they hold a slot and their paths |
| `conflicts[]` | items left out because their `task_files` overlap a lane or a running item (`item`, `with`, `reason`, `paths`) |
| `waiting[]` | phases and items that wait: `phase`, `item`, `reason` (a dependency, a gate, a running batch) |
| `deferred[]` | ready work that did not fit into `N` slots |
| `next` | the single next action of `plan.py next` without `--parallel` |

Take a lane of `kind: run-items` and conduct it with `orch conduct run --plan <plan> --items <lane items>`; a `design-phase`
lane is planning work, not a conductor run.

## Work source

`extension.json` (extension/v1, kind `command`, point `orch:work-source`, protocol 1) registers the bridge as the
work source of orch. The machine enables it in its configuration:

```toml
[aicore.plugins.planner-orch]
manifest = "<hub>/bridges/planner-orch/extension.json"
trusted = true   # passes PLANNER_ROOT, PLANNER_PLAN_PY, SKM_ORCH_ROOT, AICORE_ROOT, SKM_AICORE_EVENTS__DELIVERY
```

Untrusted, the plugin finds the planner and orch through `planner` and `orch` on `PATH`. `worksource.py` answers
`op: describe` and `op: invoke` with one plugin-response; the input and output of every op follow orch's
`schemas/work-source/v1`, and the plan is written only through `plan.py`.

| Op | What the bridge does |
| --- | --- |
| `claim` | Candidate: the first of `items`, else the item this run holds (executor session `run_id`) or already closed (`result.attempt_id` = `att-<run_id>-<item>`), else the first item of the first `run-items` lane of `plan.py next <plan> --parallel 1 --json`; none → `status: none`. An attempt id outside the planner's pattern (at most 128 characters) is `blocked` `ATTEMPT_ID_INVALID` before anything is written. Then `get` (title, route), `context --stdout` (scenario and run options, see [Orchestration of an item](#orchestration-of-an-item)), `orch.py [--config <orch_config>] policy show <scenario>`, and `start <plan> <ref> --actor <P/M/E> --session <run_id> --no-scout --json`. The actor of `start`: with `actor_source: options` (the run's `--options` name the executor) the run's actor wins over the executor of the item's `orchestration` field by field (`actor_fields`: what the run named; a partial executor such as only an effort keeps the plan's provider and model), and a replaced plan value is answered as `actor_override` (`ACTOR_OVERRIDE`: item, plan value, run value; a warning, never a refusal; the planner's class check `ROUTE_UNDERSHOOT` stays); with `actor_source: default` or none, the plan's executor, else the claimed actor. Answer `attempt_id` = `att-<run_id>-<ref>`, `session` = `run_id`, `options` (the run-option layers, general first) when any; a repeat of the same run gives the same answer, also after the item was closed by that attempt (`result.attempt_id`; no `start` then). |
| `brief` | `brief.build` in process (no plan write) → `aicore.state.blobs.put_json(..., project=<repository of the plan>)`; `plan.py add-artifact <plan> <item> --path <blob path> --role input` (a repeat is a no-op). A repeat whose brief differs only in `digest`, the `@` suffix and `provenance.source_digest` from the newest brief already declared on the item reuses that brief (declaring the brief changes the item and so the source digest). `artifact_id` = `brief-<ref with . and / as ->-<digest[:12]>`, returned to orch only (a planner artifact id names an output). |
| `register` | `register.py <plan> <ref> --report <tmp> --status S --actor <registrar> --executed-by <worker> --attempt-id <attempt_id> --evidence V#=PATH… --owner-session <run_id> --gate evidence`; `outcome` `recorded`, `no-op` (every call was a no-op) or `refused` with the code of the guard or of the refused `plan.py` call; `gate` and `receipt` from the receipt. |
| `commit` | `plan.py commit <plan> <ref> --role executor [--path P]… [--actor A] --json`: `committed` with `sha`; `NOTHING_TO_COMMIT` is `no-op` (a repeat after the commit); `OUTSIDE_SCOPE` is retried once with `--leave-outside` when the foreign paths are all plan files (the other pieces of a batch) or when the request names the paths of the piece (`paths`: anything else dirty is not its work, e.g. another session) — the left-out non-plan paths are named in `message`; any other refusal is `refused` with the planner's code. |
| `release` | `plan.py finish <plan> <ref> --status blocked --owner-session <run_id>`, then `plan.py reopen`: the planner has no verb that returns an in-progress item to `todo`, and the two together clear the executor session. An item not in progress under this run is `no-op`; a refusal of `finish`/`reopen` is `refused` with the planner's code. |
| `note` | `plan.py log <collection> <refs[0]> --type note --summary <text>`: the journal note of support work run from a file input (`orch conduct run --input`, provenance `plan_support` or `phase_support`). `refs` names a phase or an item; without one the note is `refused` with `NOTE_NO_TARGET`. A source that does not serve `note` loses only the note (`WORK_SOURCE_NO_NOTE`). |
| `research` | The research-result of a research stage of the conductor: written to `research/<item>-<n>.json` in the folder of the plan (a record of the research, not plan state) and declared with `plan.py add-artifact <plan> <item> --path <file> --role input`; a repeat of the same result is `no-op`. An unknown item, a number below 1 or a ref that is no file name is `refused` (`ITEM_UNKNOWN`, `RESEARCH_REF_INVALID`) and leaves no file. A source that does not serve `research` loses nothing: the conductor keeps the result in the artifacts of the piece (`RESEARCH_NOT_SAVED`). |

| Answer | `reason_code` |
| --- | --- |
| claim `blocked` | `SCENARIO_UNKNOWN` (no run-policy pack for the scenario), `ITEM_OWNED` (held by another session; never taken over), `ATTEMPT_ID_INVALID`, `OVERLAY_INVALID` (an orchestration overlay that is not `{"scenario"?, "options"?}` JSON), or the planner's refusal of `get`, `context` or `start` |
| register `refused` | `REGISTER_STALE_OWNER`, `REGISTER_EVIDENCE_MISSING`, `REGISTER_EVIDENCE_RED`, the other register codes above, or a refusal of `log`/`finish` (`CHECKS_RED`, `EVIDENCE_INVALID`, …) |
| protocol error | `INPUT_INVALID` (not the point or an unknown op), a brief refusal of the planner (`PHASE_NOT_DETAILED`, `READ_MISSING`, …), `BRIDGE_PARTNER_UNAVAILABLE`, `AICORE_NOT_FOUND` |

The `brief` answer also names `artifacts_dir` = `<plan dir>/artifacts/<ref>`: the orch conductor keeps the committed
artifacts of the item there (stage-report, `review-verdict.json`, check evidence); the planner's scoped commit owns
`artifacts/<item>/**`.

### Orchestration of an item

The claim reads the scenario and the run options from the context pack, level by level from the most specific: the
item, its phase, the plan.

- Fields: `orchestration.scenario` and `orchestration.options` of the item, phase and plan documents. The options are
  the planner's extension slot `orchestration.options`: this bridge supplies its schema (`bridge.json` `extends` →
  `schemas/run-options.schema.json`, a literal copy of orch's `schemas/conductor/v1/run-options.schema.json`;
  `OptionsContractTests` keep them equal), so `set` and `check` refuse options outside orch's contract. A planner that
  does not find this bridge among its `bridges.roots` refuses the options with `EXTENSION_UNAVAILABLE`.
- Overlays: knowledge documents whose id starts with `orchestration-` and that have a section `orchestration` holding
  one JSON object `{"scenario"?: name, "options"?: run-options}` (raw or in a fenced block). An overlay applies to the
  item or phase named in its `applies_to`, or to the plan when `global`. Overlays are the fallback for plan engines
  that refuse the fields (`unexpected property`, `EXTENSION_UNAVAILABLE`); they are added with `plan.py add-document`.

The scenario is the first one found from the item up, a field before an overlay of the same level, else the one the
planner resolved from its configuration (`scenario_source` `config:*`); an overlay names its source
`document:<id>`. The options become layers, general first: the plan, the phase, the item, and at each level the
overlays before the field. orch merges them over its configuration and the run-policy pack and checks every layer.

## Finding orch

`brief` needs no orch: the bridge knows the format. orch is needed only for the conformance tests.
`partners.find_orch_root()` looks for a directory with `scripts/orch.py`:

1. `SKM_ORCH_ROOT`;
2. an `orch` command on `PATH` (its real path, two levels up).

There is no search by neighbouring folders. The planner is found the same way (`PLANNER_PLAN_PY`, `PLANNER_ROOT`,
a `planner` command on `PATH`; the dispatcher sets the first two) and the foundation by `AICORE_ROOT`, then
`_vendor/aicore`, then `packages/aicore` of the hub that holds the bridge. The bridge never imports orch; it calls `python3 <orch>/scripts/orch.py validate <kind> <file>`. When orch
is required and missing, `require_orch()` prints `BRIDGE_PARTNER_UNAVAILABLE: orch not found (set
SKM_ORCH_ROOT)` and exits 3. `doctor.py` is the same lookup as a doctor row (`planner-orch.partners`, `swissknifeman doctor`). Check-evidence: the Task core checks its own field contract
(`plan.py schema check-evidence`) with any `$schema`, so exec/v1 check-evidence passes unconverted;
`test_conformance.py` proves it on orch's fixtures.

## Tests

```bash
bash bridges/planner-orch/scripts/test.sh    # with PLANNER_ROOT (and SKM_ORCH_ROOT) set
bash scripts/test-bridges.sh                 # every bridge of the hub, partners wired from the hub layout
```

`test_brief.py`, `test_register.py` and `test_commit_bridge.py` (the stage-result check skips without orch) work without orch.
`test_worksource.py` (claim, brief, register with the guards, every request and answer valid by orch's
`work-source/v1`, and describe and invoke through `aicore.ext.plugins`) runs on temporary plans and skips without orch. `test_conformance.py` (documents valid for
`orch.py validate`, lifecycle phrases of the bridge ⊇ orch's, orch check-evidence accepted by Task) and
`test_schema_profile.py` (orch's closed schema profile ⊇ Task's) skip when orch is not found.
`test_record_parity.py` pins every recording obligation W1–W12 to its owner; rows owned by orch roles or by
this repository's plan skip when those are absent. The hub runner `scripts/test-bridges.sh` runs these tests.

## launch

```text
plan.py bridge planner-orch launch <role> <provider> [--model M] [--effort E] [--cwd DIR] [--routing FILE]
```

Prints `{argv, transport, timeout_s, model, model_class}` and starts nothing. The entry comes from the partner's
launch catalog (`orch.py launch show|argv`); the catalog holds a `model_class`, never a model. The bridge maps the
class to a model through `mappings.<provider>.class_selectors` in `configs/command-routing.json` (`--routing`
overrides the file) and the effort through `effort_selectors`. `--model` pins the exact model of an owner
selector (`reviewer grok/grok-4.7`) instead of the class mapping. Grok `executor` and `bounded-implementer` resolve
their models through the mapping too, with `--model` as an explicit override. A synthetic launch entry with
`model_set: unknown` gets no model argument; `--model` there is `LAUNCH_INVALID`. Refusals: `LAUNCH_UNKNOWN` (unlisted pair),
`LAUNCH_REFUSED` (explicit catalog refusal, with `<role>/<provider>: <reason>`),
`LAUNCH_INVALID` (bad request or catalog), `LAUNCH_MODEL_UNRESOLVED` (mapping has no model for the class),
`ROUTING_UNREADABLE`.

A reviewer on another provider (`reviewer-selection`): `plan.py bridge planner-orch launch reviewer grok --model grok-4.7
--effort high --cwd <repository>`. The grok entry runs headless under orch `scripts/ro-run.py` (Linux Landlock, no
root, no user namespaces): `--protect <repository> --rw <repository>/vendor` keeps the checkout read-only except
for test caches, with default writes to temp directories, `/dev` and `~/.grok`. Protection requires ABI >= 3 and
refuses a checkout under a default writable root or an in-checkout symlink/escaping writable grant (exit 3).
The report-fixer is protected without the vendor grant and also disables shell. Both disable editing, subagents,
scheduled writes, workflows and image/video generation. Grok writers instead grant `--rw <repository>`.
The Grok `triager` has the same protection and vendor grant as the reviewer. `researcher` and `advisor` protect the
checkout without granting vendor writes, retaining shell and web search to query research sources. These roles use
jsonl (`streaming-messages-json`), read the brief from stdin (`--prompt-file /dev/stdin`) and run under
`bypassPermissions`. Conductor preflight checks the provider behind the wrapper, so a missing Grok CLI is unavailable.
`launch scout grok --cwd <repository>` succeeds with text transport (`--output-format plain`), economy/low, 300 s,
`--protect <repository>`, no checkout write grant, and web search disabled. `launch registrar grok` exits 1 with
`LAUNCH_REFUSED:`: the registrar needs plan/state writes outside the checkout. `researcher codex` and `advisor codex`
are also explicitly refused because read-only Codex has no network. The bridge preserves these catalog codes unchanged.
The tests also compare the argv of `scout` with Task's own `orchestration.scout`, which
`start --scout` keeps using unchanged.
