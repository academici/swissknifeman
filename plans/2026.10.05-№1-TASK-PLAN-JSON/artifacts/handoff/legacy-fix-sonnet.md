# Prompt for Sonnet — remove v2/migration awareness from the v3 engine (separate fix)

Run after PLAN1.P3.1 is closed, as its own commit. Not a plan item: an ordinary fix.

**Owner rule (verbatim):** «никакой миграции в коде быть не должно, мы исходим из того, что старых планов нет.
А миграция будет в ручном режиме по инструкции!!!» The v3 engine (`packages/task/lib/task/plan/`, built in
PLAN1 P1–P2) must not read, detect, adopt or mention layout v2 plans. Manual migration lives only in
`packages/task/docs/migration/v2-to-v3.md`, which writes JSON by hand and needs none of the code below.

**Owner rule 2:** all Markdown parsing of plans is removed; every interaction with a plan (read and write, by
commands, hooks, artifex, skiller, harness, tests) goes only through the `plan.py` API (`task.plan` package or the
CLI). Generated `.md` views are output only — no code may parse them.

## Findings to fix (audit by Opus, 2026-10-05)

| # | Where | Legacy | Fix |
|:--|:--|:--|:--|
| 1 | `lib/task/plan/ops.py` `_identities`, `_v2_short_id`, `_SHORT_ROW` | reads `| Short ID |` rows from v2 `plan.md` to allocate numbers | allocate only from `plan.json` (`store.short_id_of`); delete `_v2_short_id`, `_SHORT_ROW` |
| 2 | `ops.new_plan` params `plan_id`, `short_id` + docstring "adopt an existing identity (migration)"; CLI `new --plan-id/--short-id` (`cli.py:325-326`), `main()` check `args.codename or args.plan_id` | migration identity adoption | delete the params, flags and branch; `--codename` becomes required |
| 3 | `cli.py:344` `add-phase --id` "explicit phase id (migration)", `ops.add_phase(phase_id=…)` | migration | delete flag and parameter |
| 4 | `store.load_plan` hint `(layout v2: plan.md without plan.json)` (`store.py:125`); `store.resolve_plan_dir` `PLAN_NOT_V3 … is a layout v2 plan` (`store.py:179-180`) | v2 detection | plain `PLAN_NOT_FOUND`/`PLAN_INVALID`: "<path> has no plan.json"; no `plan.md` probing |
| 5 | `model.py:12` comment + `PLAN_ID` alternative `[A-Z][A-Z0-9-]+` ("historical codename-only form") | legacy id form | accept only `YYYY.MM.DD-№N-CODENAME` |
| 6 | `views.py` plan view row `| Layout | v3 |` and template making the Short ID row "readable by plan_numbering" (`tests/engine/test_views.py:63-67`) | compatibility with the v2 numbering scanner | drop the `Layout` row and the compatibility test |
| 7 | `store.py:19,26`, `cli.py:14,85`, `tests/engine/test_views.py:14` import `task.plan_numbering` (a v2 module that P3.2 deletes) | v3 depends on v2 code | move `ARCHIVE` and `find_plans_root` into `plan/store.py`; drop the imports |
| 8 | `templates/plan/agents.md` and the harness `task.plan-files` text list `_v2/` | migration leftover | remove `_v2/` (the migration doc deletes `_v2/` itself) — if P3.1 already did it, skip |
| 9 | `schemas/plan/v1/log-event.schema.json` enum `migrated` | event type for migration | keep **only** if the migration doc still writes it (it does: step 2 `log.jsonl`); otherwise remove. Decision: keep — it is data, not code |

| 10 | `packages/skiller/lib/skiller/quality/eval.py:758-770` | imports `task.task_contract.classify_tier` (v2 module, deleted in P3.2) | move the tier rule into skiller or derive it from item JSON via `plan.py show`; no `task_contract` import |
| 11 | `packages/artifex/lib/artifex/authority.py:24` (`task_contract_allow`), `dispatch.py:13` (`parent_task_contract_hash`) | v2 contract vocabulary after artifex moved to `plan.py show` | replace with item-JSON facts (status, depends_on satisfied, authority.kind/gate granted); hash = sha256 of `plan.py show <plan> <item>` output |

Any other code found by the final grep that reads `plans/**/*.md`, `journal.jsonl`, `*.state.md`, `bundles/` or
imports a v2 module (`plan_lint`, `plan_work`, `task_contract`, `plan_numbering`, `journal`, …) from outside the v2
runtime is in scope with the same fix: read through `plan.py`. Not in scope: `harness/wf_status.py` (workflow-run
journal, not plans) and `analyst/proposals.py` (docs text).

Tests to delete or rewrite: `tests/engine/test_ops.py` `test_numbering_sees_v2_plan_md_and_v3_plan_json_in_live_and_archive`,
`test_explicit_identity_adopts_an_existing_v2_directory`, `test_allocates_ordinal_and_short_id_like_plan_numbering`
(keep the allocation assertions, drop the `plan_numbering` comparison); `tests/engine/test_cli.py`
`test_new_reads_the_message_from_a_file_and_adopts_an_identity` (keep the `--message-file` part);
`tests/engine/test_store.py:157-161` (expect the generic no-plan.json error); `tests/engine/test_model.py:25`
(`LEGACY-PLAN` must now be rejected). Update `research/00-design.md` §8 CLI block only if PLAN1 is still v2
(otherwise leave plan text alone).

## Make the rule binding for the rest of PLAN1 (so later items do not repeat the mistake)

Before PLAN1 migration (it is still v2 — edit only these texts, no state):
- `research/00-design.md`: §8 delete the `import-state` line and the `[--plan-id ID --short-id PLANn]` and
  `add-phase --id` options; §9 delete the "v2 plan … stop with" paragraph; §13 drop `_v2/` from the generated list;
  add at the top of §1: "Owner rule 2026-10-05: no migration or v2-awareness in code; plans are read and written
  only through `plan.py`; no code parses plan Markdown."
- `artifacts/design/examples.md` E9: replace `(new --plan-id --short-id)` with "written by hand per the migration doc".
- `phases/P3/P3.2.md` and `phases/P4/*.md`: remove any step that relies on a v2 stop line, `import-state`,
  `--plan-id/--short-id` or parsing `.md`; P3.2 starts with the manual migration per `docs/migration/v2-to-v3.md`.
- `phases/P3/P3.2.md` Validation: add an acceptance check that proves the end state —
  `ls packages/task/lib/task` shows only `__init__.py`, `plan/`, `command_catalog.py`, `command_render.py`,
  `session_context*.py`; and `grep -rnE "plan_lint|plan_work|task_contract|plan_numbering|journal_migration|\.state\.md|bundles/" packages --include=*.py --include=*.sh`
  → empty (except `harness/wf_status.py`). The same check goes into the last item of P4.
After PLAN1 is migrated (P3.2, through the API only):
- `plan.py set PLAN1 plan --json '{"rules": [... existing ..., "No migration or v2-awareness in code; every plan read/write goes through plan.py; no code parses plan Markdown (owner, 2026-10-05)"]}'`
- `plan.py add-decision PLAN1 --title "API-only plans, no migration code" --json '{"status": "accepted", "decision": "<rule>", "rationale": "owner message 2026-10-05", "applies_to": ["P3", "P4"], "supersedes": ["D4"]}'`
  (D4 point 1 about the v2 stop line is superseded; keep the rest of D4 in the new text).

## Steps

1. `grep -rniE "v2|legacy|migrat|plan_numbering|plan\.md|adopt an" packages/task/lib/task/plan packages/task/tests/engine packages/task/templates/plan`
   — confirm the list above; anything new of the same kind is in scope.
2. Fix 1–8; keep behavior for v3 plans identical.
3. `cd packages/task && PYTHONPATH=lib:../.. python3 -m unittest discover -s tests/engine -t .` → OK, then
   `bash packages/task/scripts/validate.sh` → `validate: OK`.
4. Final grep (step 1) returns only the `migrated` enum and docs; repo-wide
   `grep -rnE "plan_lint|plan_work|task_contract|plan_numbering|\.state\.md|journal\.jsonl" packages --include=*.py | grep -v "packages/task/lib/task/\(plan_\|task_contract\|journal\)" | grep -v packages/task/tests/test_`
   shows nothing outside the v2 runtime (except `harness/wf_status.py`).
5. One commit: `refactor(task): убрать v2/миграционную логику из движка v3`.
