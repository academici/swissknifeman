# HANDOFF — 2026-08-08 — after P3.1

**Next:** «ЗАПУСК ВРУЧНУЮ: implementation/high»

## Native Codex launch-block

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high — детерминизм сборщика несёт гейт |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Approval/Sandbox | `-a never -s danger-full-access` |
| Context | NEW SESSION — manual item |
| Суть | Исполнить P3.2: построить детерминированный сборщик bundle. |
| Команда | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P3.2'` |

## Provider-neutral plan-protocol launch-block

| Параметр | Значение |
|:--|:--|
| Model | implementation |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | Исполнить P3.2: построить детерминированный сборщик bundle. |
| Команда | — |

```text
$ task:plan-run 2026.08.07-PLAN-ECONOMY P3.2
```

**Done:** P3.1 closed green. Contract `bundle` v1 is frozen in a semantic document and Draft
2020-12 JSON Schema with one illustrative example; the closed five-code failure taxonomy,
raw-byte and selected-byte integrity, declaration freshness, canonical digests, provenance,
commit policy, and rejected alternatives are explicit. Item commit: `31cf532b`.

**Remaining:** P3.2 and the remaining P3–P6 executable items.

**Sources of truth:** `root/contracts/bundle-v1.md` · `root/contracts/bundle-v1.schema.json` ·
`phases/P3/P3.1.state.md` · item commit `31cf532b`.

**Open risks:** Final `plan-lint --baseline HEAD` reports 0 errors and 4 inherited ARTIFEX
workflow-placement/name warnings, with 0 new findings. During the in-progress event the accepted P3
DoR text transiently exposed two false-positive warnings; closing P3.1 removed them. A separate
mixed-state projection defect remains: `status.md` reports P3 as `⬜ Not started` while its counter is
`1/7`, because `plan_status._phase_status` has no branch for terminal-plus-not-started items.

**Workarounds/Deferred/Open questions:**

- Workarounds: none; generated state/status were rebuilt through `plan-views.py`.
- Deferred: add the mixed terminal/not-started → `🟡 In progress` branch in
  `packages/task/lib/task/plan_status.py::_phase_status` plus a regression test in the owning task
  package; keep it outside P3.1's plan-only Files.
- Open questions: —
