# Roadmap исполнения — 2026.08.12-№1-TASK-RESILIENCE

**Статус:** design pass 2 complete; P0 закрыта по owner decision D12,
следующий executable batch — B-P1-CUTOVER (P1.1–P1.3).
Порядок фаз: P0 → P1 → P2 → P3 → P4 → P5 → P6. Batch не пересекает phase audit/close.

## Правило группировки

- Adjacent items одной фазы объединяются при общем producer/consumer, Required Reads, файлах,
  setup или Validation, если продолжение дешевле повторного холодного старта.
- Отдельные commits/Deliverables/receipts сохраняются внутри Batch и не являются причиной `solo`.
- `solo` требует конкретной границы: incompatible Exec, capability, owner/irreversible gate,
  широкая смена surface/validation или context budget.
- Запуск Batch использует максимальные model/effort/review его строк и union capabilities.
  После каждого item сохраняется тот же Batch, но команда адресует только оставшийся suffix.

## Карта исполнения

| Item | Batch | Depends on | Route | Exec | Review | Граница / reuse |
|:--|:--|:--|:--|:--|:--|:--|
| P0.1 | B-P0-EVIDENCE | — | frontier/high | manual | full | gap matrix → acceptance; 🟢 закрыт |
| P0.2 | B-P0-EVIDENCE | P0.1 | frontier/high | manual | full | reuse gap matrix; 🟢 закрыт |
| P0.3 | solo | P0.2 | frontier/high | manual | full | mandatory Perplexity capability/checkpoint |
| P1.1 | B-P1-CUTOVER | P0 | frontier/high | manual | full | единый fleet inventory context |
| P1.2 | B-P1-CUTOVER | P1.1 | implementation/high | manual | full | inventory→migration producer chain |
| P1.3 | B-P1-CUTOVER | P1.2 | implementation/high | manual | full | zero-live proof→removal без reread |
| P2.1 | B-P2-IDENTITY | P1 | implementation/high | manual | full | общий identity parser/linter |
| P2.2 | B-P2-IDENTITY | P2.1 | implementation/high | manual | full | identity grammar→qualified refs |
| P3.1 | B-P3-CONTINUE | P2 | implementation/high | manual | full | state semantics→commands |
| P3.2 | B-P3-CONTINUE | P3.1 | implementation/high | manual | full | общие commands/tests |
| P3.3 | B-P3-CONTINUE | P3.2 | implementation/high | manual | light | тот же false-stop/canon context; узкий predicate |
| P4.1 | B-P4-BLOCK | P3 | implementation/high | manual | full | candidate schema→confirmer |
| P4.2 | B-P4-BLOCK | P4.1 | frontier/high | manual | full | reuse block/RAG fixtures; route=max |
| P5.1 | B-P5-DELIVERY | P4 | implementation/high | manual | full | receipt→phase lifecycle |
| P5.2 | B-P5-DELIVERY | P5.1 | implementation/high | manual | full | общие state/fingerprint fixtures |
| P5.3 | solo | P5.2 | implementation/high | manual | full | переход на cross-package generator/docs surface |
| P6.1 | solo | P5 | implementation/high | manual | full | clean release-tree hard gate |
| P6.2 | solo | P6.1 | implementation/medium | plan-exec | full | irreversible tag + другой Exec |
| P6.3 | solo | P6.2 | implementation/high | manual | full | external rollout после verified tag |

## Точные provider-neutral запуски

| Batch | Items запуска | Route | Capabilities | Команда |
|:--|:--|:--|:--|:--|
| solo | P0.3 | frontier/high | Perplexity Web, filesystem, git | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P0.3` |
| B-P1-CUTOVER | P1.1–P1.3 | frontier/high | filesystem, git, skiller registry, maind projects | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.1-P1.3` |
| B-P2-IDENTITY | P2.1–P2.2 | implementation/high | filesystem, git | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P2.1-P2.2` |
| B-P3-CONTINUE | P3.1–P3.3 | implementation/high | filesystem, git | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P3.1-P3.3` |
| B-P4-BLOCK | P4.1–P4.2 | frontier/high | filesystem, git, isolated-child-return, RAG | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P4.1-P4.2` |
| B-P5-DELIVERY | P5.1–P5.2 | implementation/high | filesystem, git | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P5.1-P5.2` |
| solo | P5.3 | implementation/high | filesystem, git, generators | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P5.3` |
| solo | P6.1 | implementation/high | filesystem, git, validation | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P6.1` |
| solo | P6.2 | implementation/medium | filesystem, git | `task:plan-exec 2026.08.12-№1-TASK-RESILIENCE P6.2` |
| solo | P6.3 | implementation/high | filesystem, git, skiller registered channels | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P6.3` |

Фактический handoff каждого запуска добавляет native provider command и вычисленный Context.
Первый запуск после terminal design/audit использует соответствующий `cold-start-root` reason;
внутри Batch items продолжаются в том же authoritative root, пока хватает бюджета/capabilities.

## Stop boundary

Только material authority/safety/irreversible/acceptance change или подтверждённый external block
останавливает цепочку. Local/procedural/transient/RAG-provider defect сохраняет item nonterminal
и exact retry/repair Next. Push/GitHub release не авторизованы.
