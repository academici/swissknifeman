# 2026.08.12-№1-TASK-RESILIENCE — План №1 — Continue-first Task

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.08.12-№1-TASK-RESILIENCE |
| Title | План №1 — Continue-first Task |
| Layout | v2 |
| Document Type | Executable Master Plan |
| Authoring Model | frontier/high |
| Repository | swissknifeman |
| Related Packages | task · skiller · harness · maind |
| Execution Mode | phase-first, continue-root, acceptance-led |
| Target Operator Classes | implementation (exec) · economy (mechanical checks) · frontier (design/audit) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| Design Passes | 1/1 — фазы восстановлены из проверенного roadmap/runtime evidence; владелец явно потребовал полную пофазную детализацию немедленно |
| visibility | private |
| Paused By | — |

## 1. Context

Task слишком рано превращает route/tool/projection/local repair signal в terminal
`Blocked`, escalation, новый design pass или преждевременный `final`. Это создаёт петлю:
задача не началась, но уже терминальна, поэтому её нельзя безопасно продолжить.
План строит continue-first контур из семи отдельных фаз: evidence baseline, cutover v1→v2,
идентичность плана, nonterminal observations/local repair, подтверждение
реальной блокировки, terminal delivery и release/rollout. Уже написанный код
считается лишь release candidate: каждая фаза отдельно сверяет его с ТЗ и
чинит расхождения до релиза. RAG:— (repo-grounded:
`findings/00-roadmap-and-runtime-gap.md`, `research/01-target-design.md`).

## 2. Execution Rules

- Исполнять строго P0 → P1 → P2 → P3 → P4 → P5 → P6; статус берётся только из generated state.
- P1 сначала мигрирует все active v1 plans, затем удаляет v1 execution schema/path; обратный порядок запрещён.
- Любой failure signal проходит `observe → minimal reproduce → classify → act → verify`.
- Procedural/transient/dependency/tool-noise/stale projection и bounded local reversible defect чинятся inline; это nonterminal `local-repair`.
- Route rejection, pending decision, local repair и block candidate не меняют item status/attempt.
- Внешний block candidate обязан иметь verified RAG; покрытие external-класса — 100%.
- Terminal `Blocked`/escalation до одного свежего isolated reviewer verdict `JUSTIFIED` запрещены.
- `AVOIDABLE` возвращает root в repair; `INSUFFICIENT_EVIDENCE` — в сбор evidence; reviewer не даёт authority.
- Material safety/authority/frozen/public/acceptance boundary не автофиксится.
- Generated provider/docs/registry/state/bundle носители менятся только owning generator.
- Кодовая/docstring/PR/review ссылка на item: `2026.08.12-№1-TASK-RESILIENCE Pn.m`; bare `Pn.m` — только внутри этого плана.
- Каждый item получает product commit и отдельный bookkeeping commit; посторонний дифф не стейджить.
- Tag создаётся только после terminal P5.1; rollout — только по уже зарегистрированным project/channel.
- Push/GitHub release без отдельного owner instruction не выполнять.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| P0.1 | frontier/high | manual | сквозной roadmap/runtime verdict и acceptance boundary |
| P0.2 | frontier/high | manual | замораживает continue-first матрицу и внешний RAG gate |
| P1.1 | frontier/high | manual | inventory/contract всех live v1 consumers перед irreversible cutover |
| P1.2 | implementation/high | manual | deterministic active-plan migration и carrier regeneration |
| P1.3 | implementation/high | manual | удаление v1 execution schema/branches после zero-active-v1 proof |
| P2.1 | implementation/high | manual | fleet-wide identity parser/linter с Unicode/back-compat |
| P2.2 | implementation/high | manual | canonical/provider comment-reference parity |
| P3.1 | implementation/high | manual | journal/state transition semantics |
| P3.2 | implementation/high | manual | continue-first admission в пяти commands |
| P4.1 | implementation/high | manual | closed schema/reducer для terminal block authority |
| P4.2 | frontier/high | manual | isolated reviewer + 100% external RAG policy |
| P5.1 | implementation/high | manual | terminal delivery receipt и exact persisted Next |
| P5.2 | implementation/high | manual | phase candidate/audit/fingerprint lifecycle |
| P5.3 | implementation/high | manual | generated provider/docs/registry parity |
| P6.1 | implementation/high | manual | exact release tree и affected-package gates |
| P6.2 | implementation/medium | plan-exec | annotated tag после release gate |
| P6.3 | implementation/high | manual | external project rollout и post-status evidence |

## 5. Decision Log

Каталог решений: `decisions/`; собрать:
`python3 packages/task/scripts/plan-views.py decisions --plan-dir plans/2026.08.12-№1-TASK-RESILIENCE`.

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| numbered-plan-identity | v1.0.0 | candidate | plan-protocol, plan-lint, Task provider commands | P1/P4 |
| continue-first-block-policy | v1.0.0 | candidate | Task commands, journal/state, provider adapters | P2/P3/P4 |
| terminal-delivery-receipt | v1.0.0 | candidate | Task commands and provider delivery seam | P4 |

## Проверка (verification status)

- RAG: `perplexity-web` x3 degraded (1 partial, 2 no-answer) → official-domain WebSearch fallback x4 OK; выжимка и URLs в `findings/02-rag-resilience-and-schema-cutover-2026-08-12.md`.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: ничего; external fact classes покрыты official sources.
- Обходки/[POSSIBLE-DEFECT]: нет product workaround; сбой Perplexity честно зафиксирован как engine degradation.
