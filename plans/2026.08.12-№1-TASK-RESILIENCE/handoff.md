# HANDOFF — 2026-08-12 — after P1.2

**Next:** run-items: task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.3

| Параметр | Значение |
|:--|:--|
| Batch | B-P1-MIGRATOR |
| Model | frontier (`gpt-5.6-sol`) |
| Thinking | high — frozen policy and fleet admission |
| Context | continue-root |
| Суть | Зафиксировать migration policy и доказать dry-run admission зарегистрированного fleet. |
| Команда | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.3` |

Provider-neutral launch-block:

```text
$ task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.3
```

Native Codex launch-block:

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.3'
```

**Done:** P1.2 — product commit `2b85d96d`; terminal state и downstream records материализованы owning generators.

**Remaining:** P1.3 завершает Batch B-P1-MIGRATOR; затем P1.4–P1.5 выполняют controlled fleet writes и retirement.

**Sources of truth:** `plan.md` · `roadmap.md` · `phases/P1/P1.3.md` · `bundles/P1.3.json` · `phases/P1/P1.3.state.md` · `findings/06-layout-v1-routing-normalization.md` · commit `2b85d96d`.

**Open risks:** monorepo `bash packages/task/scripts/validate.sh` остаётся красным только на pre-existing archive Layout-v1 Routing rows; downstream P1.3 остаётся `unknown` до создания его policy validator.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: package docs и `CHANGELOG.md` — в policy/release контуре плана, поскольку не входят в Files P1.2.
- open_questions: —
