# Roadmap исполнения — 2026.08.10-TASK-LEAN-AUTONOMY

**Обновлён:** 2026-08-11 · **Соответствует plan.md:** D18 successor P2 после final RED P1

P0/P1 остаются историей; D17 запрещает их третий audit/repair. Новое исполнение идёт по трём
последовательным solo items с разными authoritative cwd. Batch не используется: P2.2 потребляет
terminal P2.1, а P2.3 квалифицирует оба package anchors.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1–P1.2 | history | — | — | D17 final RED | immutable provenance; не переисполнять |
| P2.1 | solo | plan-run | implementation/high | D18 | Task-owned command/schema/verifier/docs-sync; cwd `packages/task` |
| P2.2 | solo | plan-run | implementation/high | terminal green P2.1 | Harness driver/fixtures/docs/changelog; cwd `packages/harness` |
| P2.3 | solo | plan-run | implementation/high | terminal green P2.1/P2.2 | root live requalification; product writes запрещены |

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

### P2.3 — root live requalification

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.3

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | cold-start-root |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.3` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P2.3'
```

## Гейты владельца

Новых owner choices нет. D18 уже разрешает repository conflicts и successor scope. Остановка
требуется только при новой authority/security/privacy/destructive/irreversible границе либо если
исправление потребует изменить stable Intent/Files/Validation. Обычный regression остаётся в
owning item и не создаёт новый audit/design loop.
