# HANDOFF — 2026-08-13 — after P6

**Next:** design-item: task:plan-design 2026.08.12-№1-TASK-RESILIENCE P6.2

| Параметр | Значение |
|:--|:--|
| Batch | owner-gate P6 |
| Model | frontier (`gpt-5.6-sol`) |
| Thinking | high |
| Context | cold-start-root: audit-root-terminal |
| Суть | Разрешить RED-границу `v0.13.1`; рекомендован exact forward candidate и новый immutable `v0.13.2`. |
| Команда | `$ task:plan-design 2026.08.12-№1-TASK-RESILIENCE P6.2` |

Provider-neutral SCOPE-PAYLOAD:

```text
$ task:plan-design 2026.08.12-№1-TASK-RESILIENCE P6.2

РЕЖИМ: доказанная граница audit-fixer; НЕ ordinary repair-run и НЕ второй audit
ВХОД: plans/2026.08.12-№1-TASK-RESILIENCE/phases/P6/P6.md → блок `## Audit P6 — 2026-08-13 (attempt 2)`; прочитать ПЕРВЫМ
СКОУП: 1) разрешить DecisionRequest `P6-audit-v0131-validation-boundary-2026-08-13` 2) при approve спроектировать exact committed release candidate с byte-fresh plan carriers 3) выпустить новый v0.13.2, не двигая v0.13.0/v0.13.1 4) повторить все release gates на exact commit
НЕ ТРОГАТЬ: не удалять/не двигать/не перезаписывать v0.13.0/v0.13.1; P6.3/P6.4 evidence; push/GitHub release/registered rollout; P0–P5
```

Native Codex launch:

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access $'$ task:plan-design 2026.08.12-№1-TASK-RESILIENCE P6.2\n\nРЕЖИМ: доказанная граница audit-fixer; НЕ ordinary repair-run и НЕ второй audit\nВХОД: plans/2026.08.12-№1-TASK-RESILIENCE/phases/P6/P6.md → блок `## Audit P6 — 2026-08-13 (attempt 2)`; прочитать ПЕРВЫМ\nСКОУП: 1) разрешить DecisionRequest `P6-audit-v0131-validation-boundary-2026-08-13` 2) при approve спроектировать exact committed release candidate с byte-fresh plan carriers 3) выпустить новый v0.13.2, не двигая v0.13.0/v0.13.1 4) повторить все release gates на exact commit\nНЕ ТРОГАТЬ: не удалять/не двигать/не перезаписывать v0.13.0/v0.13.1; P6.3/P6.4 evidence; push/GitHub release/registered rollout; P0–P5'
```

**Done:**

- Audit attempt 2 reproduced Task aggregate exit `1` on exact tagged candidate
  `3e24951ec643ad8826cba3018883fc93acaba51f` and returned verdict RED.
- Capsule `patch-release-v1.json` now records `task_validate: 1`; P6.2 is
  `🟠 Done with deviations`; candidate rebound is
  `ec2e01d5100a9160c706c80c8a54ffb1a1380cb65b62926d099d6a35eb5ebe27`.
- Fresh isolated reviewer returned schema-valid `JUSTIFIED`.
- Resolver returned `approval_required / P5_DECISION_ESCALATED`; request
  `P6-audit-v0131-validation-boundary-2026-08-13` is durable and unresolved.
- `v0.13.0` and `v0.13.1` remain unchanged; no push, GitHub release or rollout repeat ran.

**Remaining:**

- Repository owner chooses the DecisionRequest outcome.
- Recommended on approval: design an exact byte-fresh candidate, run every release gate on
  that commit, then issue `v0.13.2` without changing older tags.

**Sources of truth:**

- `phases/P6/P6.md` final audit block; `findings/25-P6-v0131-exact-validation-audit.md`.
- `findings/24-P6.2-patch-release.md`; `artifacts/P6/patch-release-v1.json`.
- `decisions/queue.jsonl`; `decisions/_gates.md`; `phases/P6/P6.2.state.md`.

**Open risks:**

- `v0.13.1` exists locally but does not satisfy its declared aggregate Task release gate.
- Current plan lint intentionally reports one error until the owner resolves the request.

**Workarounds/Deferred/Open questions:**

- workarounds: none; overlaying later plan carriers is explicitly forbidden.
- deferred: `v0.13.2`, push, GitHub release, registered-project rollout repeat.
- open_questions: owner choice for the durable DecisionRequest.
