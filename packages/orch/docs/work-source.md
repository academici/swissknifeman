# Work source

A work source supplies the work of orchestration runs and records their outcome. orch opens the extension point
`orch:work-source` (`unit.json` `provides.extension_points`); a command plugin of `aicore.ext.plugins` serves it.
The configuration key `work_source` of `[orch]` names the plugin (default `planner-orch`, the bridge between the
planner and orch); the plugin itself is registered by the machine in `[aicore.plugins.<id>]`. orch never names the
source or reads its files: it speaks the contract below.

## Contract `work-source/v1`

`schemas/work-source/v1/input.schema.json` (`urn:swissknifeman:orch:work-source:input:v1`) and
`output.schema.json` (`…:output:v1`), contract `urn:swissknifeman:orch:work-source`, alpha. Both are closed and
choose a branch by `op`.

| Op | Input | Output |
| --- | --- | --- |
| `claim` | `plan`, `plans_root?`, `items?` (candidate refs in order), `batch?`, `scenario?` (the invocation's `--scenario`: wins over the scenario the source resolves), `run_id`, `submission_id`, `actor` (`provider`, `model`, `effort?`), `orch_config?` (the invocation configuration of the orch command, for the source's own calls to orch) | `status` `claimed` \| `none` \| `blocked`; `ref`, `title`, `scenario`, `scenario_source`, `route`, `depends_on?` (the pieces it depends on: the conductor holds it when one of them ended blocked in the run), `attempt_id`, `session` when claimed; `reason_code`, `message` when blocked |
| `brief` | `plan`, `plans_root?`, `ref`, `unit?`, `run_id` | `input_ref` (`artifact-ref/v1`), `input_id`, `digest`, `reused`, `artifact_id` |
| `register` | `plan`, `plans_root?`, `ref`, `run_id`, `attempt_id`, `status` (`done` \| `done_with_deviations` \| `blocked`), `report`, `evidence` (`{"V<n>": path}`), `registrar`, `executed_by` | `outcome` `recorded` \| `no-op` \| `refused`; `gate` (`verdict` `pass` \| `missing` \| `red` \| `stale` \| `none`, `checks` `{"V<n>": exit or null}`); `receipt?`; `reason_code`, `message` when refused |
| `commit` | `plan`, `plans_root?`, `ref`, `run_id`, `attempt_id`, `paths` (extra owned paths, such as the artifact folder), `actor?` | `outcome` `committed` \| `no-op` \| `refused`; `sha` when committed; `reason_code`, `message` when refused |
| `release` (optional) | `plan`, `plans_root?`, `ref`, `run_id`, `reason?`, `actor?` | `outcome` `released` \| `no-op` (the run does not hold the piece) \| `refused`; `reason_code`, `message` when refused |
| `note` (optional) | `collection`, `plans_root?`, `text`, `refs` (a phase or an item of the collection), `run_id?`, `actor?` | `outcome` `recorded` \| `no-op` \| `refused`; `reason_code`, `message` when refused |
| `research` (optional) | `plan`, `plans_root?`, `ref`, `run_id`, `number` (from 1), `result` (a `research-result`), `actor?` | `outcome` `recorded` \| `no-op` (the same result is already kept) \| `refused`; `path` (repository-relative) when kept; `reason_code`, `message` when refused |

A claim may also answer `options`: the run-option layers of the work, general first (`[{source, options}]`, each a
conductor `run-options` document that orch validates). A brief may answer `artifacts_dir`: the repository folder
where a run keeps the committed artifacts of the work (stage-report, review verdict, check evidence). Without it the
conductor keeps them in `.swissknifeman/orch-artifacts/<run>/<ref>/`: local records, not committed (ignored like the
state folder). A `register` answer may name `evidence` (`{V#: path}`): where the source keeps the evidence of the work for
good (the planner bridge copies the evidence of a workspace plan into the plan folder); the conductor then records
those paths.

`run_id` uses the characters of an attempt id (`[A-Za-z0-9._:-]`, at most 100) because the attempt id
`att-<run_id>-<ref>` is built from it. A refusal of the source is an answer with a `reason_code`. A plugin that fails, answers an error or answers
outside the contract is a failure of the source.

## Client

`orch.worksource.PluginWorkSource(plugin_id, *, project=None, env=None, config_file=None)` implements the
`WorkSource` protocol (`claim(**fields)`, `brief(**fields)`, `register(**fields)`, `commit(**fields)`, `release(**fields)`, `note(**fields)`, `research(**fields)`, each returning
the output document). Every call looks the registration up again, validates the request (`INPUT_INVALID`, nothing is sent),
describes and invokes the plugin through `aicore.ext.plugins.invoke_one`, and validates the answer.

| Code | Meaning |
| --- | --- |
| `WORK_SOURCE_UNAVAILABLE` | no registration of the plugin, a disabled or unusable one, or a plugin without the point |
| `WORK_SOURCE_FAILED` | the plugin failed, answered an error, or answered outside `work-source/v1` |
| `INPUT_INVALID` | orch built a request outside `work-source/v1` |

## The cycle: `orch.py source`

Between `source prepare` and `source register` a session, a person or the [conductor](conductor.md) does the work.
`--config FILE` applies to every command.

```text
orch.py source claim (--plan P | --input FILE [--commit]) [--plans-root DIR] [--item REF]… --actor P/M[/E] [--submission-id SUB]
orch.py source brief --run RUN
orch.py source prepare --run RUN --provider P [--binding B] [--model-catalog FILE]
orch.py source register --run RUN --report FILE --status S [--evidence V#=PATH]… --actor P/M[/E] [--executed-by P/M[/E]]
orch.py source commit --run RUN [--path PATH]… [--actor P/M[/E]]
orch.py source release --run RUN [--reason TEXT] [--actor P/M[/E]]
orch.py source research --run RUN --result FILE --number N [--actor P/M[/E]]
```

- `claim` derives `submission_id` = `sub-` + the first 24 hex characters of the SHA-256 of the canonical JSON
  `{plan, items, actor}` (unless given) and `run_id` = `run-` + the first 24 hex characters of the SHA-256 of the
  submission, so the same arguments give the same run. A claimed run writes `run.json` (`run_id`, `submission_id`,
  `plugin`, `plan`, `plans_root`, `ref`, `attempt_id`, `scenario`, `session`) in the run directory and emits
  `orch.run.started` once per attempt; a blocked claim emits `orch.run.refused` (step `claim`). The answer is printed
  with `run_id` and `submission_id`. A repeated claim of a run asks the source for the run's own item, so a run never
  moves on to other work after its item is closed.
  With `--config FILE` the claim passes the file as `orch_config`, so the scenario check of the source sees the same
  run-policy packs.
- `brief` stores the brief through the source and records `input_ref` and `input_id` in `run.json`.
- `prepare` reads the brief from the artifact store of the project, loads the run-policy pack of the run's scenario
  (`orch.py policy show`), prepares a dry run with `out = <run>/prepare` and the run's `submission_id`, and writes
  `launch-plan.json`. A refusal emits `orch.run.refused` (step `prepare`).
- `register` sends the report and the evidence, writes `receipts/register.json`, and emits
  `orch.run.stage.finished` (stage `primary`) and `orch.run.finished` when something was recorded, or
  `orch.run.refused` (step `register`). A repeat that the source records as `no-op` emits nothing.
- `commit` asks the source for one commit of the registered work and writes `receipts/commit.json`; nothing left
  to commit is `no-op`, a refusal exits 1.
- `release` gives a claim back to the source and writes `receipts/release.json`: the piece goes back to the state
  before the claim, so that a later run can claim it (`ITEM_OWNED` no longer holds). The op is optional: a source that
  does not serve it answers `INPUT_INVALID`/`WORK_SOURCE_FAILED`, which the conductor reports as `CLAIM_KEPT` and goes on.

The run directory is `<project>/.swissknifeman/state/orch/runs/<run_id>/` inside a project (a git repository or a
folder with `.swissknifeman`), else under the machine state. Exit codes: 0 ok (`claimed`, `none`, `recorded`,
`no-op`), 1 refusal (`blocked`, `refused`, `RUN_UNKNOWN`, `RUN_NOT_BRIEFED`, `BRIEF_UNAVAILABLE`, a prepare
refusal), 2 usage, 3 `WORK_SOURCE_UNAVAILABLE`.

## The built-in file source

`--input FILE` (`orch.py source claim --input`, `orch conduct run --input`) serves one execution-input document with no plan:
`orch.worksource_file.FileWorkSource`, the same protocol and contract, checked on both sides. `claim` always succeeds for the one
input (the reference is its `input_id`; a different candidate is `INPUT_UNKNOWN`; an input outside `exec/v1` is `INPUT_INVALID`);
`brief` is the document itself in the artifact store (a file that changed since the claim is `INPUT_CHANGED`, a failure of the
source); `register` applies the same evidence gate as the planner bridge (check-evidence with exit 0 for every acceptance
check) and writes `stage-report.json`, `evidence/V#.json` and `register.json` (the idempotency receipt) into
`.swissknifeman/orch-artifacts/<run_id>/<input_id>/` (local records, not committed); `commit` commits nothing unless `--commit`, then only the given paths with
`adhoc(<input_id>): <title>`; `release` is a no-op; `note` is `refused` (`NOTE_UNSUPPORTED`): a file has no journal; `research` keeps `research-<n>.json` in the artifact folder of the input. For provenance
`plan_support` and `phase_support` the `register` command forwards the note to the configured plugin source
(the CLI prints the answer with `note: {outcome: recorded | unsupported | refused, message?}`; `receipts/register.json` keeps the pure answer of the source and the note goes to `receipts/note.json`). The `input_id` of a file input names the artifact folder, so it must be one path component (`INPUT_INVALID` otherwise); `commit` uses literal git pathspecs, and a commit refused by a hook leaves the index as it was. `run.json` of the cycle gets
`source = {kind: file, path, commit}` and `plugin: file`; the later commands read it.

## Ownership and integrity

- One owner per attempt: the claim starts the work under the session `run_id`; work held by another session is
  `blocked` (`ITEM_OWNED` for the planner); the port never takes work over.
- Fencing: `register` is refused (`REGISTER_STALE_OWNER`, gate `stale`) when the work is no longer held by the
  run, for example after another session took it over; the planner bridge checks it before any write and again in
  the closing `finish` under the plan lock.
- Evidence gate: `done` and `done_with_deviations` need a check-evidence file with exit 0 for every acceptance
  check (`REGISTER_EVIDENCE_MISSING`, `REGISTER_EVIDENCE_RED`); a claim in the report without a file is not a
  result. `blocked` needs none.
- Idempotency: a repeated claim of the same run returns the same attempt; a repeated register of the same attempt
  is `no-op`; a repeated brief with unchanged inputs reuses the stored brief.
