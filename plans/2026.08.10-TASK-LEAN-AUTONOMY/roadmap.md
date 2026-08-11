# Roadmap исполнения — 2026.08.10-TASK-LEAN-AUTONOMY

**Обновлён:** 2026-08-11 · **Соответствует plan.md:** D25 P3.4 bounded repair → fresh P3.2 attempt 2

P0/P1/P2 остаются историей; D17 запрещает третий audit/repair P1 и P2. P3 audit-1 RED
открывает ровно один solo P3.4: product-free Validation/provenance repair на committed amendment
anchor. После его terminal bookkeeping commit отдельный native process выполняет P3.2 attempt 2.
Batch нет: committed-input и fresh-session boundaries не допускают same-session grouping.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1–P2.4 | history | — | — | D17/D23 final RED | immutable provenance; не переисполнять |
| P3.1/P3.3/P3.2 attempt 1 | history | — | — | Audit P3 RED + D25 | append-only evidence; не запускать как qualification |
| P3.4 | solo | plan-run | implementation/high | committed D25/spec/bundle/handoff | focused Validation + append-only P3.1/P3.3 reconciliation; cwd `packages/task`; product writes нет |
| P3.2 attempt 2 | solo | plan-run | implementation/high | terminal committed P3.4 + distinct fresh native session | root live requalification; новый report only |

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

Owner choices D23–D25 приняты. P3.1/P3.3/P3.2 attempt 1 — history, не runnable Next.
P3.4 требует committed plan-only amendment; P3.2 attempt 2 — committed terminal P3.4 и
отдельный fresh native process. Если P3.4 или финальный audit-2 non-GREEN, автоматического
третьего repair/audit нет.

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

### P3.2 attempt 2 — fresh root requalification

**Next:** waiting: terminal committed P3.4 → run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.2

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | cold-start-root: capability-missing |
| Команда | — |

```bash
# НЕ раньше: P3.4 terminal report/state/handoff находятся в committed HEAD
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P3.2'
```
