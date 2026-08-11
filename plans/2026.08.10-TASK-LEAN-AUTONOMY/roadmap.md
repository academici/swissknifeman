# Roadmap исполнения — 2026.08.10-TASK-LEAN-AUTONOMY

**Обновлён:** 2026-08-11 · **Соответствует plan.md:** D26 owning repair → P3.2 → direct phase close

P0/P1/P2 остаются историей. D26 заменяет для P3 terminal audit-loop: отдельный native process
чинит owning source/provider/cache defects, выполняет P3.2 requalification и в том же root
закрывает P3. Новый audit, repair item, formal handoff или deferred branch не создаются.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1–P2.4 | history | — | — | D17/D23 final RED | immutable provenance; не переисполнять |
| P3.1/P3.3/P3.2 attempt 1 | history | — | — | Audit P3 RED + D25 | append-only evidence; не запускать как qualification |
| P3.4 | solo | plan-run | implementation/high | committed D25/spec/bundle/handoff | focused Validation + append-only P3.1/P3.3 reconciliation; cwd `packages/task`; product writes нет |
| P3.2 terminal closure | solo | plan-run → plan-close P3 | implementation/high → implementation/low | committed D26 + distinct fresh native session | owning repair, full requalification, direct close без audit |

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

Owner choices D23–D26 приняты. P3.1/P3.3/P3.2 attempt 1 — append-only history, не runnable Next.
P3.2 выполняется из committed D26 отдельным fresh native process; любой in-scope red чинится
на месте и повторяется до green, после чего тот же root вызывает `task:plan-close P3`.

### P3.4 — Validation/provenance repair

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.4

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | cold-start-root: capability-missing |
| Команда | — |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman/packages/task -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.4'
```

### P3.2 — terminal closure

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.2

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | cold-start-root: capability-missing |
| Команда | — |

```bash
# НЕ раньше: D26/spec/bundle находятся в committed HEAD
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.2'
```
