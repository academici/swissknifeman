# Review verdict: P10.10

Reviewer: grok/grok-4.7/high (headless, read-only launch via the orch bridge `launch reviewer grok --model grok-4.7
--effort high`, argv in argv.json). Route proven from the reviewer's own session record
`~/.grok/sessions/<cwd>/01a1297e-8932-7c61-8e83-12e3eeed0caa/`: `modelId` grok-4.7 (result `modelUsage`
grok-4.7-build), `reasoning_effort` high, `contextWindowTokens` 500000. Stream: review-grok-4.7.stream.jsonl
(56 turns, 29 min). Verdict: 6 findings, all confirmed by the executor (code reading and a regression test that
reproduces the reviewer's scenario) and fixed in one correction.

1. Plugin claim repeated with the same run_id and no items after the item was closed took the next ready item.
   Fix: the candidate search finds the item the run holds (executor session) or already closed (`result.attempt_id`
   = `att-<run_id>-<item>`) through the planner engine, before the ready lanes. Test:
   `test_a_repeat_without_items_after_the_registration_is_the_same_claim`.
2. A schema-valid run_id with `@` produced an attempt id outside the output contract after the item had started.
   Fix: `work-source/v1` run_id uses the attempt-id characters `[A-Za-z0-9._:-]`. Test:
   `test_run_ids_are_attempt_id_characters_with_room_for_the_reference`.
3. A maximum-length run_id made an attempt id longer than the planner's 128 characters, so the item could be claimed
   but never registered. Fix: run_id at most 100 characters, and the plugin refuses `ATTEMPT_ID_INVALID` before
   `start` when the attempt id does not fit the planner pattern. Test:
   `test_an_attempt_id_the_planner_cannot_take_is_blocked_before_start`.
4. The evidence gate accepted any JSON with check_id and exit, then `log` was written and `finish` refused
   `EVIDENCE_INVALID`. Fix: the gate proves each file with the planner's own `lifecycle.load_evidence` (the contract
   `finish` applies); an invalid file is `REGISTER_EVIDENCE_MISSING` before any write. Test:
   `test_a_file_that_is_not_check_evidence_is_missing_and_nothing_is_logged`.
5. `orch.py --config` did not reach the scenario check of the plugin (`orch.py policy show`). Fix: optional claim
   input `orch_config`, passed by `orch.py source claim` and given to `orch.py --config` by the plugin. Test:
   `test_the_invocation_configuration_of_orch_reaches_the_scenario_check`.
6. Fencing was read once before the writes; a take-over between the guard and `finish` still closed the item.
   Fix: planner `finish --owner-session SESSION` refuses `ITEM_OWNED` under the plan lock (a repeat of the recorded
   attempt stays a no-op); the bridge passes it to `finish` and reports `REGISTER_STALE_OWNER` with gate `stale`.
   Tests: planner `test_finish_with_owner_session_fences_the_old_owner`, bridge
   `test_a_take_over_after_the_guard_is_fenced_by_finish` (a plan.py wrapper takes the item over right before
   `finish`). `log` calls made inside that window remain in the journal (documented).

Before the verdict arrived the executor also fixed, on its own, a repeated `orch.py source claim` moving a closed run
to the next item (the CLI now asks the source for the run's own item); the reviewer saw that change mid-run.

After the correction: V1 (orch tests and validate), V2 (bridges: OK), V3 (e2e work source: OK), V4 (planner validate in
a sandbox), V5 components (ecosystem-units check and render, hygiene, standalone orch, every scripts/test-*.py) green;
golden is red only for three files the owner has uncommitted. No second review round was run: each finding is a local
fix covered by a regression test that replays the reviewer's reproduction.
