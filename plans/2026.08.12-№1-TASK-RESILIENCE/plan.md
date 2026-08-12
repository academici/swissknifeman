# 2026.08.12-№1-TASK-RESILIENCE — План №1 — Continue-first Task

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.08.12-№1-TASK-RESILIENCE |
| Title | План №1 — Continue-first Task |
| Version | 1.0.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | frontier/high |
| Last Updated | 2026-08-12 |
| Repository | swissknifeman |
| Related Packages | task · skiller · harness · maind |
| Execution Mode | one-phase, continue-root, owner-requested fast path |
| Target Operator Models | implementation/high · frontier/high |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| Design Passes | 1/1 — одна фаза и три items; владелец явно запросил немедленный полный цикл |
| Paused By | — |

## 1. Context

Живые прогоны `task` показывают повторяющийся класс: route/tool/projection/local syntax signal
превращается в terminal `Blocked`, повторный design или audit loop до доказательства реальной
границы. Части continue-first политики уже появились в plan-protocol, но journal/state reducer,
block confirmation и terminal delivery не обеспечивают её структурно. Параллельно прежний D3
архивного `2026.07.25-ECO-OPT` реализовал только full PLAN-ID references и отверг требуемый теперь
порядковый номер. План закрывает оба класса одной компактной фазой, готовит minor-релиз и rollout.
RAG:— (repo-grounded: `findings/00-roadmap-and-runtime-gap.md:1`).

## 2. Execution Rules

- Работать P0.1 → P0.2 → P0.3 в одном authoritative root; между items сохранять commit boundary.
- Любой failure signal проходит `observe → minimal reproduce → classify → act → verify`.
- Local reversible/procedural/transient/dependency signal не терминализирует item.
- External block candidate обязан иметь RAG evidence; покрытие внешних block candidates — 100%.
- `Blocked`/escalation до isolated reviewer verdict `JUSTIFIED` запрещены; reviewer не авторизует.
- `AVOIDABLE` возвращает owning root в repair; `INSUFFICIENT` — в сбор evidence, оба nonterminal.
- Generated provider/docs/registry artifacts меняются только owning generators.
- Полные ссылки на items в комментариях/docstrings: `2026.08.12-№1-TASK-RESILIENCE Pn.m`.
- Внешние writes rollout выполняются только штатными worktree-local CLI и после release commit/tag.
- Посторонний дифф не коммитить, не stash/revert; stage только exact paths item'а.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| B0 | P0.1 | implementation/high | manual | full | новый fleet-wide identity contract и back-compat lint |
| B0 | P0.2 | frontier/high | manual | full | новый deterministic block policy и state semantics |
| B0 | P0.3 | implementation/high | manual | full | provider delivery, generated parity, docs и release gates |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Continue-first Task release | 0/3 | 🟡 In progress |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-08-12 | supersedes `2026.07.25-ECO-OPT` D3 в части отказа от ordinal: новые планы используют `YYYY.MM.DD-№N-CODE`, Title `План №N — …`; кодовые комментарии используют полный `<PLAN-ID> Pn.m`. **Consequences:** новый ID содержит Unicode `№`; CLI/lint/tests обязаны доказать round-trip, старые IDs остаются readable. | Прямая директива владельца; full ID без ordinal формально был реализован, но требуемая визуальная/дневная нумерация отсутствует. RAG:— (repo-grounded: `brief/00-brief.md:12`, `plans/archive/2026.07.25-ECO-OPT/plan.md:234`). |
| D2 | 2026-08-12 | Полный дизайн и исполнение идут одной фазой/одним root без дополнительных design passes. | Три независимых, последовательно совместимых item и явный запрос «максимально быстро». RAG:— (owner-grounded: `brief/00-brief.md:18`). |
| D3 | 2026-08-12 | Journal разделяет observation и terminal outcomes; route rejection, pending decision, local repair и block candidate не меняют state/attempt. | Устраняет детерминированную петлю `не начал → Blocked → нельзя повторить`. RAG:— (repo-grounded: `findings/00-roadmap-and-runtime-gap.md:12`). |
| D4 | 2026-08-12 | Terminal block разрешает только reducer после isolated reviewer `JUSTIFIED`; внешний класс дополнительно требует verified RAG evidence. | Separate agent проверяет гипотезу, но authority остаётся у deterministic root policy; неподтверждённый блок продолжает repair/evidence. RAG:— (owner-grounded: `brief/00-brief.md:8`). |
| D5 | 2026-08-12 | Изменение выпускается как minor `v0.12.0`; после terminal plan archive тег ставится на release commit, затем зарегистрированные проекты обновляются по их существующему channel. | Меняется framework capability/schema; release-discipline классифицирует это как minor. RAG:— (repo-grounded: `packages/skiller/skills/repository-bootstrap/release-discipline/SKILL.md:45`). |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-08-12 | plan-designer/frontier/high | Design pass 1/1: План №1 создан и полностью детализирован; ACTIVE переключён с `—`. |
| 2026-08-12 | executor/gpt-5.6-sol | P0.1 закрыт: numbered PLAN-ID, Title/comment contract и Unicode lint GREEN; см. Completion Notes. |
| 2026-08-12 | executor/gpt-5.6-sol | P0.2 закрыт: observation events не терминализируют item; isolated review/RAG gate доказан тестами. |
| 2026-08-12 | executor/gpt-5.6-sol | P0.3 закрыт: terminal receipt, provider parity и v1/v2 audit candidate, docs/roadmap и release metadata GREEN; см. Completion Notes. |

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| numbered-plan-identity | v1.0.0 | delivered | plan-protocol, plan-lint, provider commands | registry/provider projections regenerated |
| continue-first-block-policy | v1.0.0 | delivered | task commands, journal/state, provider adapters | P0.3 подключает command/provider surfaces |
| terminal-delivery-receipt | v1.0.0 | delivered | task commands/provider delivery | generated Claude/Codex projections + docs |

## Audit design — 2026-08-12

**Verdict:** GREEN

- Brief coverage: все пять owner outcomes закрыты P0.1–P0.3 и D1–D5.
- Traceability: roadmap evidence привязаны к item `Why`/`Inputs`; historical D3 superseded явно.
- Feasibility: все изменения имеют package-owned seams, validators и generator paths; runtime остаётся stdlib-only.
- Safety: authority/safety gates не ослабляются; reviewer даёт evidence verdict, но не authorization.
- Boundary: provider transport heartbeat/final hook не заявлен как доступный; P0.3 доказывает package-owned receipt и честно оставляет transport remainder.
- Lint: 0 errors; единственный warning — bootstrap-цель P0.1 (`№N` ещё не принят current validator).
- Candidate fingerprint: `sha256:4151ea38b45ef9148bf401ad312da279afb08fa26f64c2354837fe7530d9c9ca`.

**Provider-neutral continuation:** `$ task:plan-run 2026.08.12-№1-TASK-RESILIENCE P0.1 P0.2 P0.3`

**Native Codex launch:** `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.12-№1-TASK-RESILIENCE P0.1 P0.2 P0.3'`
