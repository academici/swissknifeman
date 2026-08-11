# Roadmap исполнения — 2026.08.10-TASK-LEAN-AUTONOMY

**Обновлён:** 2026-08-11 · **Соответствует plan.md:** Design Pass 2/2 + final inline F20/cross-project D12/D13 refinement

Roadmap сохраняет adaptive order внутри item'а, но не объединяет разные package cwd. Каждый
launch читает root→cwd instructions, исполняет один Task Contract и закрывает item отдельно.
Cursor, lease, finish-manifest и новый orchestration runtime не вводятся.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1 | solo | plan-run | implementation/high | — | solo: Harness instruction + D13 root run-report scope, обязательный `packages/harness` cwd; P0.2 ждёт terminal state |
| P0.2 | solo | plan-run | implementation/high | — | solo: Skiller D12 adaptive canon/generator scope, обязательный `packages/skiller` cwd |
| P1.1 | solo | plan-run | implementation/high | — | solo: Task D11–D14 command/runtime/context/lifecycle, включая pre-close audit gate и recovery-only item close, + canonical docs + factual root `[Unreleased]` до D9; обязательный `packages/task` cwd |
| P1.2 | solo | plan-run | implementation/high | единый D9+D13 committed ledger; затем GO/ADJUST по D8/D10–D13 | solo: repository-root causal canary + stop-tax evidence; не пишет package code/changelog и не поглощает foreign `docs/reference.md` diff |

## Готовые launch-block'и

### P0.1 — Harness instruction canon + root run evidence

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P0.1

**Provider-neutral plan-protocol launch block**

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root |
| Суть | reason=`owner-pause-no-resume`; выполнить P0.1 instruction thinning + D13 root run evidence только из Harness package cwd |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P0.1` |

**Native Codex launch block**

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-terra | high | `cold-start-root` (`owner-pause-no-resume`) | P0.1, Harness instruction + run-report scope | `codex -C /home/vostrikov/projects/packages/swissknifeman/packages/harness -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P0.1'` |

### P0.2 — Skiller plan canon

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P0.2

**Provider-neutral plan-protocol launch block**

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root |
| Суть | reason=`capability-missing`; текущий Harness root не несёт Skiller package rule stack |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P0.2` |

**Native Codex launch block**

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-terra | high | `cold-start-root` (`capability-missing`) | P0.2, Skiller-only scope | `codex -C /home/vostrikov/projects/packages/swissknifeman/packages/skiller -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P0.2'` |

### P1.1 — Task command/runtime alignment

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.1

**Provider-neutral plan-protocol launch block**

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root |
| Суть | reason=`capability-missing`; текущий Skiller root не несёт Task package rule stack |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.1` |

**Native Codex launch block**

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-terra | high | `cold-start-root` (`capability-missing`) | P1.1, Task D11–D13 runtime/lifecycle scope | `codex -C /home/vostrikov/projects/packages/swissknifeman/packages/task -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.1'` |

### P1.2 — root field canary

**Next:** waiting: единый D9+D13 committed-ledger prerequisite green → run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2

**Provider-neutral plan-protocol launch block**

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root |
| Суть | reason=`capability-missing`; canary владеет repository-root evidence, не Task package source |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2` |

**Native Codex launch block**

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-terra | high | `cold-start-root` (`capability-missing`) | P1.2, one real D10–D13 causal/stop-tax canary | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2'` |

```bash
# НЕ раньше: единый D9+D13 six-URL gate находится в committed HEAD:docs/reference.md
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2'
```

## Гейты владельца

До P1.2 repository owner/владелец foreign `docs/reference.md` diff отдельно reconciles и commits
единый D9+D13 set из шести exact official URLs. P1.2 проверяет только committed `HEAD`; red оставляет item not-started и
waiting, не поглощая dirty carrier. После зелёного D9+D13 gate P1.2 GO закрывает item только при всех
зелёных predicates, exact D10 observed/not-observed values и D12/D13 causal scorecard. ADJUST создаёт ровно один durable
owner DecisionRequest по D8, оставляет P1.2 nonterminal и публикует структурный waiting Next;
автоматический design/audit loop запрещён без D3 material trigger. Factual `[Unreleased]` запись
уже закрыта P1.1 и при ADJUST не удаляется; P1.2 её не пишет.
