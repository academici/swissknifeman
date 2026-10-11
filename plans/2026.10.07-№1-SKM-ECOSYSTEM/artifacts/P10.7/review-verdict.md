# Review P10.7 (grok-4.7, effort high requested)

Reviewer session: grok `01a128dc-8062-7f11-b3c3-183de3ae4d4a` (headless, read-only launch from the orch bridge `launch`).
Route proof from the session record: `modelId` grok-4.7 (updates.jsonl), `contextWindowTokens` 500000 (signals.json). The reasoning effort `high`
is in the launch argv (`argv.json`); the session record does not store it, so it is not independently proven.

Reviewer ran `test.sh` (328 tests), `validate.sh` and `orch.py policy test` (11 cases): green. Report: `review-report.txt`.

## Findings and the executor's confirmation (own runs)

1. `settings.py` `_dirs` — a relative `profiles.dirs` entry was resolved from the folder of the layer that last wrote the array, so an
   invocation `_append` retargeted a machine-file relative folder to the invoker's tree. CONFIRMED: machine `dirs = ["team-policies"]` plus an
   invocation `_append` gave `<invocation dir>/team-policies`. Fix: a relative entry is refused (`PROFILES_DIR_RELATIVE`), only absolute or `~` paths
   are accepted; the CLI reports the code. Tests `test_a_relative_profile_folder_is_refused`,
   `test_an_appended_folder_cannot_retarget_a_relative_one_of_a_lower_layer`, `test_an_appended_absolute_folder_follows_the_lower_one`,
   `test_a_relative_pack_folder_is_an_error`.

After the fix: `test.sh` + `validate.sh` (331 tests), V2, ecosystem-units and public-hygiene green; aicore tests green (1414). One round, one owning correction; no re-review requested.
