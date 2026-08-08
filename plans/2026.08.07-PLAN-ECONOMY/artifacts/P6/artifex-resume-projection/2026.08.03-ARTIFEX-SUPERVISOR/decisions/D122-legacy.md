---
id: D122
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-GRANT:G-OWNER-P5.2-RETRY] Asked what to do about the `claude-code` wall-clock budget if a fresh batch is granted, the owner literally selected «Поднять до 600000 ms в новых строках (реком.)», having already selected the option whose own text authorizes «новый `[OWNER-GRANT]` на три ЗАМЕНЯЮЩИЕ строки P5.2 (новые trial ID, append под новым грантом)» (`brief/34-p5.2-zero-accept-owner-decision-2026-08-06.md`, both answers quoted verbatim there). The grant authorizes exactly three replacement P5.2 repository-slice trials — new distinct trial IDs, one slice each, `reusable:false`, same three scenarios/file scopes/frozen base `bde07fb0` and same two providers as the spent v1 rows, with the `claude-code` row's `timeout_ms` raised from `180000` to `600000` and every other cap unchanged. They are minted by P5.1 into an ADDITIVE v2 carrier set (own catalog/request/grants/replay/admissions/index files, own `catalog_hash`) so that not one v1 byte and not one existing `task_hash` moves. Scope of the grant, exhaustively: three dispatches, one fresh process each, no retry of a started attempt, no fourth slice, no raw provider content, no change to provider pins, no D105 row consumption, no extension of D105's `2026-08-12T23:59:59Z` expiry or its 14-row count. The three spent v1 P5.2 rows stay spent and are not re-minted, reset or reused; they remain historical evidence of the null measurement. **Consequences:** P5.2's acceptance is now judged against the v2 rows, so `validate-repository-pilot.py` must pin the v2 admission index and the raised budget explicitly rather than inheriting v1 constants; the raised `600000` ms applies only to the new `claude-code` row and creates no precedent for P5.3/P5.4, whose rows keep `180000`; if the fixed prompt still produces a `WALL_TIMEOUT` at 600000 ms, that is a first-class provider fact rather than a confounded one (`findings/P5.2-task-description-gap-2026-08-06.md` F5). RAG:— (owner-grounded: `brief/34-p5.2-zero-accept-owner-decision-2026-08-06.md` Q1/Q2 literal answers; repo-grounded: spent v1 rows in `artifacts/P5/repository-pilot-results-v1.json`, D105 carrier set and `phases/P5.md` P5.1).

## Почему

Only a fresh, separately identified batch can turn a null measurement into a real one, and raising exactly the one budget that produced an uninterpretable observation — while changing nothing else — keeps the retry a controlled experiment rather than a second variable-rich attempt.
