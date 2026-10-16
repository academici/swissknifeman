# Review P10.4 (grok-4.7, effort high)

Reviewer session: grok `01a125ca-78bd-7e32-b045-07b2d13405e2` (headless, read-only launch from the orch bridge `launch`).
Route proof from the session record: `current_model_id` grok-4.7, `reasoning_effort` high, `contextWindowTokens` 500000.

## Reviewer report

The identity-key table assigns the wrong repeat behavior to `correlation_id` and `causation_id`.

- `packages/orch/docs/contracts.md:177` and `packages/orch/docs/contracts.md:181` — The repeat column treats `correlation_id` as the submission idempotency key ("returns the existing run") and `causation_id` as the event deduplication key ("an identical repeat is ignored"), and the event row omits the conflict case. The field descriptions in the same change say `correlation_id` is the submission the event belongs to, `causation_id` is the causing event, and only `event_id` ignores an identical repeat and conflicts on different content.

REPRODUCTION:

```bash
python3 - << 'PY'
from pathlib import Path
lines = Path("packages/orch/docs/contracts.md").read_text().splitlines()
for n in (177, 181):
    print(f"contracts.md:{n}: {lines[n-1]}")
schema = Path("packages/orch/schemas/exec/v1/run-event.schema.json").read_text().splitlines()
for n in (105, 109, 113):
    print(f"run-event.schema.json:{n}: {schema[n-1].strip()}")
defs = Path("packages/orch/schemas/exec/v1/defs.schema.json").read_text().splitlines()
print(f"defs.schema.json:217: {defs[216].strip()}")
PY
```

```
contracts.md:177: | submission | `submission_id`, `correlation_id` | `sub-` + `[A-Za-z0-9._-]` (≤ 120) | returns the existing run |
contracts.md:181: | event | `event_id`, `causation_id` | `evt-` + `[A-Za-z0-9._:-]` (≤ 200) | an identical repeat is ignored |
run-event.schema.json:105: "description": "Key of this event; an identical repeat is ignored, different content under the same key is a conflict."
run-event.schema.json:109: "description": "Key of the event that caused this one."
run-event.schema.json:113: "description": "Submission this event belongs to."
defs.schema.json:217: "description": "Caller-supplied submission key: repeating a submission returns the existing run.",
```

The schemas, semantic checks, fixtures, and compatibility compare did not show a further defect. `aicore schema compat` against `HEAD` and against `origin/ecosystem-split` reports 18 `property-added` notes, 0 warnings, 0 errors. Existing `$defs` are unchanged. Patterns match the specified classes, including the 120 and 200 bounds, `/` only on `attemptId`, and `:` on attempt, call, and event. `KEY_REUSED` fires for every pair among `submission_id`, `run_id`, `attempt_id`, `call_id`, and `event_id`, and it stays quiet for a document that only has `run_id` and for every previous valid fixture. `owner_epoch` values `true`, `false`, and `1.0` fail as `type`; `0` and `-1` fail as `EPOCH_INVALID` on run-event, stage-result, and effect-receipt. The registry loads 14 schemas from `/tmp` with no duplicate `$id`. `bash packages/orch/scripts/validate.sh` and `python3 scripts/public-hygiene.py` both pass (182 tests).

VERDICT: FINDINGS

## Executor disposition

Finding 1 (contracts.md identity-key table, repeat behaviour of `correlation_id` and `causation_id`): CONFIRMED by reading the file
against the schema descriptions. Fixed in `packages/orch/docs/contracts.md` (rows now say `submission_id` returns the existing run,
`correlation_id` only names the submission; `event_id` ignores an identical repeat and conflicts on different content,
`causation_id` names the causing event). Documentation-only; no re-review needed (first round, one correction).
