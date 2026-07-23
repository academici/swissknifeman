# Roadmap исполнения — 2026.07.23-FLEET-DUAL-PROVIDER

**Обновлён:** 2026-07-23 · **Соответствует plan.md:** v0.9.0

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P0.1 | solo | plan-run | frontier/high | — | 🟢 attempt 3 закрыт: generated core содержит runtime tree; объединять нельзя |
| P0.2 | solo | plan-run | implementation/high | — | меняет fleet eligibility semantics |
| P1.1 | solo | plan-exec | implementation/medium | — | 🟢 D9 disposable synthetic conformance MVP закрыт; весь live rollout остаётся P2 |
| P1.2 | conditional solo | plan-run | implementation/high | D6/frozen-contract change only | ⛔ пропущен по D9: GREEN P1.1 не создал concrete owning defect |
| P2.1 | solo | plan-exec | implementation/medium | — | 🟢 plan-only traceability prerequisite закрыт; live access остаётся только P2.2 |
| P2.2 | solo | plan-run | frontier/high | D14 scope change | 🟠 internal owning fixes закрыты; live consumer rollout deferred |

## Готовые launch-block'и групп

### P0.2 — regression и fleet dry-run

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | Проверить package regression и повторить no-write fleet dry-run с provider-qualified skip evidence. |

```
$ task:plan-run 2026.07.23-FLEET-DUAL-PROVIDER P0.2
```

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| P1.2 escalation | Только изменение frozen provider contract | P2 до новой D-записи |

### P1.1 — replacement pilot

**Next:** exec-items: task:plan-exec 2026.07.23-FLEET-DUAL-PROVIDER P1.1

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | same-session — item |
| Суть | Запустить один D9 disposable synthetic conformance MVP; live fleet rollout не входит и остаётся P2. |

```text
$ task:plan-exec 2026.07.23-FLEET-DUAL-PROVIDER P1.1
```

### P1 закрыта — независимый аудит

**Next:** audit-phase: task:plan-audit 2026.07.23-FLEET-DUAL-PROVIDER P1

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | — |
| Context | cold-start — plan-step |
| Суть | Независимо проверить terminal P1 по committed conformance evidence и D9 skip boundary. |

```text
$ task:plan-audit 2026.07.23-FLEET-DUAL-PROVIDER P1
```

Audit P1 завершён ATTENTION; remediation carrier — P2.1, P1 не
реопеняется.

### P2.1 — P1.1 traceability prerequisite

P2.1 закрыт item commit `906dddc6`; carrier:
`findings/P2.1-p1-traceability.md`. Следующий executable item — P2.2.

### P2 items terminal — phase close

**Next:** close: task:plan-close 2026.07.23-FLEET-DUAL-PROVIDER P2

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | low |
| Capabilities | — |
| Context | cold-start — phase close |
| Суть | Сверить terminal P2 items, закрыть фазу с D14 deviation и подготовить независимый audit carrier. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="low"' -a never -s danger-full-access 'NEW SESSION: Close phase P2 of plan 2026.07.23-FLEET-DUAL-PROVIDER with task:task-plan-close. Reconcile terminal P2 items, commits 8f91865e, 63edc6da and 48c7abbe, package validation evidence, D14 material deferral and plan lint; then hand off to an independent P2 audit. HARD BOUNDARY: do not inspect, mutate or validate any live consumer repository; never use --repair or --force; preserve D5-D7.'
```
