# Roadmap исполнения — 2026.08.12-№1-TASK-RESILIENCE

**Статус:** design pass 2 complete; P0–P5 терминальны; P6.1 закрыт, а P6.2–P6.4
перепроектированы после post-P6.1 effective-route/schema repair: requalification → tag → rollout.
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
| P1.1 | B-P1-MIGRATOR | P0 | frontier/high | manual | full | closed producer; единый fleet inventory context для P1.2–P1.3 |
| P1.2 | B-P1-MIGRATOR | P1.1 | implementation/high | manual | full | узкая Routing compatibility на общих migrator tests |
| P1.3 | B-P1-MIGRATOR | P1.2 | frontier/high | manual | full | frozen policy + 15 previews; reuse matrix/migrator context |
| P1.4 | B-P1-FLEET | P1.3 | implementation/high | manual | full | external-write boundary, apply previews и zero-live ledger |
| P1.5 | B-P1-FLEET | P1.4 | implementation/high | manual | full | zero-live proof→removal без повторной fleet reconnaissance |
| P2.1 | B-P2-IDENTITY | P1 | implementation/high | manual | full | общий identity parser/linter |
| P2.2 | B-P2-IDENTITY | P2.1 | implementation/high | manual | full | identity grammar→qualified refs |
| P3.1 | B-P3-CONTINUE | P2 | implementation/high | manual | full | state semantics→commands |
| P3.2 | B-P3-CONTINUE | P3.1 | implementation/high | manual | full | общие commands/tests |
| P3.3 | B-P3-CONTINUE | P3.2 | implementation/high | manual | light | тот же false-stop/canon context; узкий predicate |
| P4.1 | B-P4-BLOCK | P3 | implementation/high | manual | full | candidate schema→confirmer |
| P4.2 | B-P4-BLOCK | P4.1 | frontier/high | manual | full | reuse block/RAG fixtures; route=max |
| P5.1 | solo | P4 | implementation/high | manual | full | terminal before D24 redesign; frozen receipt evidence has no reusable execution suffix |
| P5.2 | solo | P5.1 | implementation/high | manual | full | historical terminal block + D24 redesign require a dedicated recovery launch; focused producer acceptance, P5.3 nonterminal dependency |
| P5.3 | solo | P5.2 | implementation/high | manual | full | package-scope restart в `packages/skiller` + cross-package generated/provider/docs aggregate gate |
| P6.1 | solo | P5 | implementation/high | manual | full | clean release-tree hard gate |
| P6.2 | solo | P6.1 | implementation/high | manual | full | post-P6.1 fix требует полной release requalification |
| P6.3 | solo | P6.2 | implementation/medium | plan-exec | full | irreversible tag по exact compact candidate |
| P6.4 | solo | P6.3 | implementation/high | manual | full | external rollout после verified tag capsule |

## Точные provider-neutral запуски

| Batch | Items запуска | Route | Capabilities | Команда |
|:--|:--|:--|:--|:--|
| solo | P0.3 | frontier/high | Perplexity Web, filesystem, git | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P0.3` |
| B-P1-MIGRATOR | P1.2–P1.3 | frontier/high | filesystem, git, Task package validation | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.2-P1.3` |
| B-P1-FLEET | P1.4–P1.5 | implementation/high | filesystem, git, skiller registry, maind projects, decision queue | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.4-P1.5` |
| B-P2-IDENTITY | P2.1–P2.2 | implementation/high | filesystem, git | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P2.1-P2.2` |
| B-P3-CONTINUE | P3.1–P3.3 | implementation/high | filesystem, git | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P3.1-P3.3` |
| B-P4-BLOCK | P4.1–P4.2 | frontier/high | filesystem, git, isolated-child-return, RAG | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P4.1-P4.2` |
| solo | P5.2 | implementation/high | filesystem, git, Task focused validation | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P5.2` |
| solo | P5.3 | implementation/high | filesystem, git, skiller canon, owning generators | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P5.3` |
| solo | P6.1 | implementation/high | filesystem, git, validation | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P6.1` |
| solo | P6.2 | implementation/high | filesystem, git, package validation, owning generators | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P6.2` |
| solo | P6.3 | implementation/medium | filesystem, git | `task:plan-exec 2026.08.12-№1-TASK-RESILIENCE P6.3` |
| solo | P6.4 | implementation/high | filesystem, git, skiller registered channels | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P6.4` |

Фактический handoff каждого запуска добавляет native provider command и вычисленный Context.
Первый запуск после terminal design/audit использует соответствующий `cold-start-root` reason;
внутри Batch items продолжаются в том же authoritative root, пока хватает бюджета/capabilities.

## Stop boundary

Только material authority/safety/irreversible/acceptance change или подтверждённый external block
останавливает цепочку. Local/procedural/transient/RAG-provider defect сохраняет item nonterminal
и exact retry/repair Next. Phase audit не передаёт ordinary repair другому root: он чинит,
валидирует и пересобирает candidate сам до final verdict. Push/GitHub release не авторизованы.
