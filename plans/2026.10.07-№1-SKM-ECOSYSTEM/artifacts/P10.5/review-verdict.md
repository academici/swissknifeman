# Review P10.5 (grok-4.7, effort high)

Reviewer session: grok `01a125e1-ed90-7881-a293-69caf8d47b7b` (headless, read-only launch from the orch bridge `launch`).
Route proof from the session record: `current_model_id` grok-4.7, `reasoning_effort` high, `contextWindowTokens` 500000.

## Reviewer report

The freshness check accepts schema-valid timestamps it cannot parse, and the new condensed check can crash validation.

1. `packages/orch/lib/orch/contracts.py:246` — `_parse_ts` only accepts whole seconds or one to six fractional digits, so a `ts` value with seven or more fractional digits (the `defs` pattern `(?:\.\d+)?`) is treated as missing and `CAPABILITY_FRESHNESS` stays silent when `fresh_until` is earlier.
   REPRODUCTION:
   ```text
   PYTHONPATH="packages/orch/lib:packages/aicore/lib" python3 - << 'PY'
   import json
   from pathlib import Path
   from orch import contracts
   rec = json.loads(Path("packages/orch/fixtures/exec/v1/valid/capability-record/probed-fresh.json").read_text())
   rec["observed_at"] = "2026-10-10T12:00:00.123456789Z"
   rec["fresh_until"] = "2026-10-10T11:00:00.123456789Z"
   print("issues", [(i.path, i.code, i.message) for i in contracts.validate(rec, "capability-record")])
   PY
   ```
   Output: `issues []`. The same record with `.5` or with `fresh_until` one second earlier returns `CAPABILITY_FRESHNESS`. The new tests only use `.5` and whole seconds, which `%f` parses.

2. `packages/orch/lib/orch/contracts.py:260` — `_condensed` catches only `TypeError`, so a lone surrogate in the required part raises `UnicodeEncodeError` out of `validate` when `digest` is absent.
   REPRODUCTION: same `PYTHONPATH`, load `fixtures/exec/v1/valid/execution-input/condensed.json`, drop `digest`, set `goal` to `json.loads('"\\ud800"')`.
   Output: without `condensed`, `['required']`. With `condensed`: `UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' in position 522: surrogates not allowed`.

3. `packages/orch/schemas/exec/v1/launch-plan.schema.json:283` — `config.values` is a new object with no `additionalProperties: false`, so an unknown key whose value is a float validates, and the open-object list in `packages/orch/docs/contracts.md:13` does not name it.
   REPRODUCTION: load `fixtures/exec/v1/valid/launch-plan/dry-run-proof.json`, set `config.values` to `{"not-a-key": {"n": 1.5}}`, call `contracts.validate(plan, "launch-plan")`.
   Output: `[]`.

4. `packages/orch/fixtures/exec/v1/valid/launch-plan/dry-run-proof.json:79` — `config.digest` and `digests.config` are not the sha256 of the canonical JSON of `config.values`, which is what the schema description at `launch-plan.schema.json:280` states. `test_launch_plan_digest_is_the_canonical_digest` only asserts the two fields are equal.
   REPRODUCTION: `aicore.util.digest.sha256_hex(canonical_json_bytes(fixture["config"]["values"]))`.
   Output: claimed `b79606fb3afea5bd1609ed40b622142f1c98125abcfe89a76a661b0e8e343910`, canonical values `398e3f95f18fc90d8a04330e3717f6dc2fe2ed37eba96c186edce0e28f55da18`.

Verified: `bash packages/orch/scripts/test.sh` and `validate.sh` (200 tests, OK); `python3 scripts/public-hygiene.py` (0 violations). `schemacompat` against `HEAD` and `origin/ecosystem-split` reports only property-added, enum-widened, and the one known `oneof-changed` on `execution-input` provenance branch 0. Every existing valid fixture still validates, including `plan-bound` with no `commit`. `on_error` rejects a class outside the 13-name enum (`property_name`), including names that match `^[a-z_]+$`, and checks `action`, `max`, and extra fields on an allowed class. `required_digest` matches an independent canonical hash of the eight keys, omits absent keys, keeps `null`, encodes bools as `true`/`false`, and turns a float into `CONDENSED_REQUIRED_DRIFT`. `inferred` with `declared` is allowed. Equal timestamps, including `.1` and `.100000`, are allowed. An empty or missing `fallback_routes` with action `fallback_route` is `FALLBACK_UNDECLARED`. A non-dict document, an int, and a bool do not crash. The registry loads `permissions` and `capability-support` from `/` and `/tmp` and returns the cached object. `datetime | None` sits behind `from __future__ import annotations`, the same form already used on `validate`. This interpreter is Python 3.12.3.

VERDICT: FINDINGS

## Executor disposition

All four findings CONFIRMED by the executor's own run and fixed in one correction (round 1; no re-review requested):

1. `_parse_ts` accepted only up to six fraction digits (CONFIRMED: issues `[]` for nine digits). Now parses whole seconds and compares fraction digits of any length; test `test_capability_freshness_compares_any_number_of_fraction_digits`.
2. `_condensed` caught only `TypeError` (CONFIRMED: `UnicodeEncodeError`; the existing `_execution_input` digest check had the same crash, found while reproducing). Both now catch `(TypeError, ValueError)`; test `test_lone_surrogate_is_reported_not_raised`.
3. `config.values` is an intentionally open map (the digest pins it): documented in the open-objects list of `docs/contracts.md`; no schema change. The same list now names `precondition.observed_prior` and the new shared definitions.
4. Fixture `dry-run-proof.json`: `config.digest` / `digests.config` are now the sha256 of the canonical JSON of `config.values`; the test asserts it.
