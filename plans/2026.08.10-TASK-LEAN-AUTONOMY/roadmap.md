# Roadmap исполнения — 2026.08.10-TASK-LEAN-AUTONOMY

**Обновлён:** 2026-08-11 · **Соответствует plan.md:** D24 P3.3 native-launch repair перед final P3.2

P0/P1/P2 остаются историей; D17 запрещает третий audit/repair P1 и P2. Новое исполнение идёт по
трём последовательным solo items P3. Batch не используется: P3.3 заменяет недостижимый provider
probe, P3.2 потребляет terminal P3.1/P3.3 и квалифицирует полный post-P2.3 anchor. Fresh native
launch provenance обязателен, но не выдаётся за runtime telemetry.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1–P2.4 | history | — | — | D17/D23 final RED | immutable provenance; не переисполнять |
| P3.1 | solo | plan-run | implementation/high | D23 + provider-bound route | Task fail-closed route, bundle dedupe, provider/docs projections; cwd `packages/task` |
| P3.3 | solo | plan-run | implementation/high | D24 + fresh native launch | Task route repair; cwd `packages/task` |
| P3.2 | solo | plan-run | implementation/high | terminal green P3.1/P3.3 + fresh native launch | root live requalification; product writes запрещены |

## Готовые launch-block'и

### P2.1 — Task contract integrity

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.1

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | continue-root |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.1` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman/packages/task -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.1'
```

### P2.2 — Harness driver integrity

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.2

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | cold-start-root |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.2` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman/packages/harness -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.2'
```

### P2.3 — Task owner-status regression

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.3

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | cold-start-root: capability-missing |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.3` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman/packages/task -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.3'
```

### P2.4 — root live requalification

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.4

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | cold-start-root: capability-missing |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.4` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.4'
```

## Гейты владельца

Owner choices D23/D24 приняты. P3.3/P3.2 требуют fresh native launch with `-m` and
`model_reasoning_effort`; это launch provenance, не runtime telemetry. Любая необходимость изменить
stable Intent/Files/Validation P3 либо принять красный required gate снова требует владельца.

### P3.1 — Task fail-closed and projection recovery

**Next:** waiting: provider-bound model class+effort текущего Codex thread доступны → run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.1

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | cold-start-root (`capability-missing`) |
| Команда | — |

```bash
# НЕ раньше: provider-bound model class+effort текущего Codex thread доступны
codex -C /home/vostrikov/projects/packages/swissknifeman/packages/task -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.1'
```

### P3.2 — root final requalification

**Next:** waiting: terminal green P3.1/P3.3 → run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.2

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | continue-root |
| Команда | — |

```bash
# НЕ раньше: terminal green P3.1/P3.3; fresh native launch selects model and effort
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.2'
```

### P3.3 — native launch provenance repair

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.3

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | continue-root |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.3` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman/packages/task -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.3'
```
