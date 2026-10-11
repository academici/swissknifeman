# Run-policy packs

A run-policy states which stages a run has and what happens when one cannot run. A **pack** is a folder named by
the policy id:

```text
<policy_id>/
  policy.json        # run-policy of exec/v1 with a semantic "version"
  cases/<case>.json  # expectations checked by `orch.py policy test`
```

`policy_id` in `policy.json` must equal the folder name (otherwise `POLICY_INVALID`) and `version` is required.

## Shipped packs

| Id | Stages that use a model | Review |
| --- | --- | --- |
| `solo` | primary | off |
| `scout-solo` | scout (economy), primary | off |
| `frontend-bounded` | scout (economy), primary (frontier), bounded implementer (economy) | off |
| `review-only` | reviewer | off |
| `full` | optional condense (economy), primary, optional review on an independent provider | on, at most 2 rounds and 1 correction |

`full` runs context (deterministic), condense (optional, `on_unavailable: skip`), primary, checks, review (optional),
registrar and git. Its `on_error` table holds the default action of each failure class, `budgets` set
`brief_max_bytes` 65536, `packer_input_max_bytes` 262144 and `stage_tokens_max` 0 (no limit), and `retries_budget.total_max` is 2.

The files in `fixtures/exec/v1/valid/run-policy/` stay as examples of the contract; the packs are the ones that run.

## Discovery

The shipped folder `configs/run-policies/` comes first, then the folders of `profiles.dirs` in order. A pack is a
subfolder with a `policy.json` and a name that is a policy id. When an id repeats, the first pack wins and orch
prints `POLICY_SHADOWED: <id> in <dir> is shadowed by <dir>` to stderr. A listed folder that does not exist prints
`POLICY_DIR_MISSING`.

## Cases

```json
{
  "description": "What the case shows.",
  "input": "fixtures/exec/v1/valid/execution-input/plan-bound.json",
  "provider": "claude-code",
  "binding": "native",
  "expect": {
    "result": "ok",
    "stages": ["primary"],
    "refusals": [],
    "policy_decision": "allow"
  }
}
```

A case runs a dry-run preparation of the policy with the input, the engine (`binding`, default `native`) and the
provider, using the role manifests and the model catalog packaged with orch and aicore, and compares the outcome with
`expect`:

| Key | Meaning |
| --- | --- |
| `result` | `ok` (a launch-plan) or `refused` (preparation raised an error); required |
| `error` | port error code of a refusal, such as `CAPABILITY_UNSUPPORTED` |
| `stages` | ids of the stages that use a model, in order |
| `refusals` | `[{stage_id, capability}]` of the stages that were dropped or refused |
| `policy_decision` | `allow` or `refuse` |

Only the keys that are present are compared. `input` is an absolute path, a path relative to the pack, or a path
relative to the orch package. A pack without cases fails `policy test`.

## Commands

```bash
orch.py [--config FILE] policy list [--json]      # id, version, case count, source, description
orch.py [--config FILE] policy show <id>          # the run-policy as JSON; exit 1 and POLICY_UNKNOWN when unknown
orch.py [--config FILE] policy test [<id> …] [--json]   # exit 1 when a case fails
```

`policy show <name>` also answers whether a scenario name is known: exit 0 means a pack with that id exists.

## Errors

| Code | Meaning |
| --- | --- |
| `POLICY_UNKNOWN` | no pack has the id |
| `POLICY_INVALID` | the policy breaks `exec/v1`, has no version, differs from its folder name, or a case is malformed |
| `POLICY_SHADOWED` | warning: an earlier pack has the same id |
| `POLICY_DIR_MISSING` | warning: a listed folder does not exist |
