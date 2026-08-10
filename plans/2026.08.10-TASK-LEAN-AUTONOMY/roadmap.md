# Roadmap исполнения — 2026.08.10-TASK-LEAN-AUTONOMY

**Обновлён:** 2026-08-10 · **Соответствует plan.md:** Design Pass 2/2

Roadmap сохраняет adaptive order внутри item'а, но не объединяет разные package cwd. Каждый
launch читает root→cwd instructions, исполняет один Task Contract и закрывает item отдельно.
Cursor, lease, finish-manifest и новый orchestration runtime не вводятся.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1 | solo | plan-run | implementation/high | — | solo: Harness-only source scope и обязательный `packages/harness` cwd; P0.2 ждёт terminal state |
| P0.2 | solo | plan-run | implementation/high | — | solo: Skiller-only canon/generator scope и обязательный `packages/skiller` cwd |
| P1.1 | solo | plan-run | implementation/high | — | solo: Task-only command/runtime scope и обязательный `packages/task` cwd |
| P1.2 | solo | plan-run | implementation/high | GO/ADJUST по D8 | solo: repository-root evidence; зависит от terminal P1.1 и не пишет package code |

## Готовые launch-block'и

### P0.1 — Harness instruction canon

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P0.1

**Provider-neutral plan-protocol launch block**

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root |
| Суть | reason=`owner-pause-no-resume`; выполнить P0.1 только из Harness package cwd |
| Команда | `$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P0.1` |

**Native Codex launch block**

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-terra | high | `cold-start-root` (`owner-pause-no-resume`) | P0.1, Harness-only scope | `codex -C /home/vostrikov/projects/packages/swissknifeman/packages/harness -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P0.1'` |

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
| gpt-5.6-terra | high | `cold-start-root` (`capability-missing`) | P1.1, Task-only scope | `codex -C /home/vostrikov/projects/packages/swissknifeman/packages/task -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.1'` |

### P1.2 — root field canary

**Next:** run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2

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
| gpt-5.6-terra | high | `cold-start-root` (`capability-missing`) | P1.2, root evidence-only scope | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2'` |

## Гейты владельца

Промежуточных гейтов нет. P1.2 GO закрывает item только при всех зелёных predicates. ADJUST
создаёт ровно один durable owner DecisionRequest по D8, оставляет P1.2 nonterminal и публикует
структурный waiting Next; автоматический design/audit loop запрещён без D3 material trigger.

